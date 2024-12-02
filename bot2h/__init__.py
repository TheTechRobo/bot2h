import json
import argparse
import typing
import asyncio
import logging
import shlex
import inspect
import logging
import functools

import aiohttp

logger = logging.getLogger(__name__)

__all__ = ["Bot", "Prefix", "StatusCodeError", "MessageSendError"]

class StatusCodeError(Exception):
    def __init__(self, code: int):
        self.code = code

    def __repr__(self):
        return f"StatusCodeError({self.code})"

class MessageSendError(Exception): pass

async def retrying_jsonl(url: str):
    tries = 0
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise StatusCodeError(response.status)
                    async for line in response.content:
                        yield json.loads(line.decode())
            except StatusCodeError as e:
                if e.code > 400 and e.code < 500:
                    # Client error
                    raise
            except Exception:
                logging.exception("Error occured in h2ibot stream")
            to_sleep = min(64, 2**tries)
            logging.warning(f"Sleeping {to_sleep} seconds before retrying")
            await asyncio.sleep(to_sleep)
            tries += 1

class Prefix(str): pass

class Command:
    parser: typing.Optional["ArgumentParser"]

    def __init__(self: "Command", match: str | Prefix, r, required_modes):
        self.match = match
        self.runner = r
        self.required_modes = required_modes
        self.help = self.runner.__doc__
        self.parser = None
        self.raw = False

    def validate_default_arg_type(self, args, ran):
        argspec = inspect.getfullargspec(self.runner)
        # Take the number of arguments, subtract the number of arguments with default values, then subtract
        # the number of arguments that are not from the message.
        minArgs = len(argspec.args) - len(argspec.defaults or ()) - 3
        if argspec.varargs:
            maxArgs = 5000
        else:
            maxArgs = len(argspec.args) - 3
        if len(args) < minArgs:
            return f"Not enough arguments for command {ran}."
        if len(args) > maxArgs:
            return f"Too many arguments for command {ran}."
        return None

    async def __call__(self: "Command", user, ran, *args):
        if modes := self.required_modes:
            success = False
            for mode in modes:
                if mode in user['modes']:
                    success = True
            if not success:
                yield f"You don't have the required permissions to use this command. ({self.required_modes})"
                return

        if self.raw:
            gen = self.runner(self, user, ran, " ".join(args))
        elif self.parser:
            args = shlex.split(" ".join(args)) # split using shell splitting instead of by spaces
            #args = [arg for arg in args if arg != ""]
            try:
                parsed = self.parser.parse_args(args)
            except ArgumentParsingError as e:
                for line in self.parser.format_usage().strip().split("\n"):
                    yield line
                yield e.msg.strip()
                return
            gen = self.runner(self, user, ran, parsed)
        else:
            if error := self.validate_default_arg_type(args, ran):
                yield error
                return
            gen = self.runner(self, user, ran, *args)
        async for msg in gen:
            yield msg

    def make_raw(self):
        if self.parser:
            raise ValueError("cannot use raw and argparse modes at once")
        self.raw = True

    def make_argparse(self, command_name):
        if self.raw:
            raise ValueError("cannot use raw and argparse modes at once")
        if not self.parser:
            self.parser = ArgumentParser(prog=command_name)

    def add_argument(self, *args, **kwargs):
        if self.raw:
            raise ValueError("cannot use raw and argparse modes at once")
        if not self.parser:
            raise ValueError("must use make_argparse before (below) add_argument")
        self.parser.add_argument(*args, **kwargs)

class Bot:
    get_url: str
    post_url: str
    send_session: typing.Optional[aiohttp.ClientSession]
    commands: list[Command]

    def __init__(self, get_url, post_url):
        self.get_url = get_url
        self.post_url = post_url
        self.send_session = None
        self.commands = []

    async def send_message(self, message):
        if not self.send_session:
            self.send_session = aiohttp.ClientSession()
        async with self.send_session.post(self.post_url, data=message) as response:
            if response.status != 200:
                raise MessageSendError(response.status)

    def command(self, f=None, *, match=None, requiredModes=None):
        if f and isinstance(f, (str, set, Prefix)):
            return functools.partial(self.command, match=f)
        elif f:
            if (not match):
                raise ValueError("match arg is required")
            cmd = Command(match, f, requiredModes)
            cmd.__name__ = match
            self.commands.append(cmd)
            return cmd
        raise ValueError("first arg must be function or match")

    def lookup_command(self, command: str):
        for runner in self.commands:
            if isinstance(runner.match, Prefix):
                if command.startswith(runner.match):
                    return runner
            elif isinstance(runner.match, str):
                if command == runner.match:
                    return runner
            elif type(runner.match) == set:
                for match in runner.match:
                    if command == match:
                        return runner
            else:
                # theoretically unreachable
                raise AssertionError("Task failed spectacularly.")

    async def handle_irc_line(self, line):
        command = line['command']
        if command == "PRIVMSG":
            user = line['user']
            message = line['message']
            args = message.split(" ")
            if runner := self.lookup_command(args[0]):
                logging.debug(f"Running handler command {runner.__name__}")
                try:
                    async for message in runner(user, args[0], *args[1:]):
                        if isinstance(message, str):
                            message = (user['nick'], message)
                        if ping := message[0]:
                            message = f"{ping}: {message[1]}"
                        else:
                            message = message[1]
                        await self.send_message(message)
                except Exception:
                    await self.send_message(f"{user['nick']}: An error occured when processing the command.")
                    logging.exception(f"Exception occured in command processor for {args[0]}")

    async def run_forever(self):
        async for message in retrying_jsonl(self.get_url):
            try:
                await self.handle_irc_line(message)
            except Exception:
                logging.exception("Exception occured when handling IRC line")

    def argparse(self, command: typing.Optional[Command] = None, command_name: typing.Optional[str] = None):
        """
        Sets the parse mode to argparse. The function signature will look like this:
        async def foo(self: Bot, user, ran, args: Namespace)
        command_name is purely cosmetic and is used in the usage message.
        """
        if not command:
            if not command_name:
                raise TypeError("command_name argument is required")
            return functools.partial(self.argparse, command_name=command_name)
        if not command_name:
            raise TypeError("command_name argument is required")
        command.make_argparse(command_name)
        return command

    def raw(self, command: Command):
        """
        Sets the parse mode to raw. The function signature will look like this:
        async def foo(self: Bot, user, ran, message: str)
        `ran` will still be separate from `message`.
        """
        command.make_raw()
        return command

    def add_argument(self, *args, **kwargs):
        """
        Identical to argparse.ArgumentParser.add_argument.
        Must use make_argparse first (below).
        """
        def ret(command: Command):
            command.add_argument(*args, **kwargs)
            return command
        return ret

class ArgumentParsingError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __repr__(self):
        return f"ArgumentParsingError({repr(self.msg)})"

class ArgumentParser(argparse.ArgumentParser):
    def __init__(self, prog=None):
        super().__init__(prog=prog, add_help=False, allow_abbrev=False)

    def error(self, message):
        raise ArgumentParsingError(message)
