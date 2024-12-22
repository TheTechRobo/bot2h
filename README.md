# bot2h
bot2h is a Python interface to http2irc focusing on simplicity.

## Getting started
A simple bot might look like this:

(p is the person, b is the bot.)

```python
import asyncio

from bot2h import Bot

bot = Bot(H2IBOT_GET_URL, H2IBOT_POST_URL)

# <p> !hello
# <b> p: Hello!
# <b> p: This command takes no arguments!
@bot.command("!hello")
async def hello(self: Bot, user, ran):
    yield "Hello!"
    yield "This command takes no arguments!"

# <p> !firstchar egg
# <b> p: The first character of egg is e.
@bot.command("!firstchar")
async def goodbye(self: Bot, user, ran, arg):
    yield f"The first character of {arg} is {arg[0]}."

# <p> !manyargs a b c d e f g
# <b> p: You provided 7 arguments.
@bot.command("!manyargs")
async def manyargs(self: Bot, user, ran, *args):
	yield f"You provided {len(args)} arguments."

asyncio.run(bot.run_forever())
```

Commands are considered in the order they are declared. So if you have this code:

```python
@bot.command("!foo")
async def hello(self: Bot, user, ran):
	yield "Bar!"

@bot.command("!foo")
async def hello(self: Bot, user, ran):
    yield "Baz!"
```

the response for `!foo` will be `Bar!`.

If you want to ping someone else:

```python
# <p1> !greet p2
# <b > p2: p1 loves you!
@bot.command("!greet")
async def goodbye(self: Bot, user, ran, target_user):
    yield target_user, f"{user['nick'] loves you!"
```

Or no one at all:

```python
# <p> !die
# <b> I am now dead.
@bot.command("!die")
async def goodbye(self: Bot, user, ran, target_user):
	yield None, "I am now dead."
```

Or even CTCP ACTION (/me):

```python
# <p> !die
# * b is now dead.
@bot.command("!die")
async def goodbye(self: Bot, user, ran, target_user):
	yield ME, "is now dead."
```

Can't spell? Use a prefix!

```python
# <p> !shdiuahiudhiuhsaawgef
# <b> p: 0 items in the queue.
@bot.command(Prefix("!s"))
async def status(self: Bot, user, ran, target_user):
```

## Parsing modes
The default parsing mode splits the message into spaces, uses the first item as the command, and then maps it to a functions arguments. You won't ever have to deal with users giving you too many or too few arguments unless you use variadic arguments (`*args`), as bot2h will provide a nice error message.

However, sometimes you will want a more sophisticated system. bot2h supports giving you either the raw message, or leveraging argparse to parse the arguments for you.

Take these as an example.

```python
# <p> !argparse https://google.com
# <b> The URL is https://google.com.
# <p> !argparse https://google.com --user-agent "InconspicuousScraper/1.0"
# <b> The URL is https://google.com.
# <p> !argparse https://google.com --user-agent "InconspicuousScraper/1.0" --verbose
# <b> p: usage: !argparse [--user-agent USER_AGENT] url
# <b> p: unrecognized arguments: --verbose
@bot.add_argument("--user-agent")
@bot.add_argument("url")
@bot.argparse("!argparse") # the name provided here is used in the usage message
@bot.command("!argparse")
async def argparse(self: Bot, user, ran, args):
    yield f"The URL is {args.url}."

# <p> !raw hello goodbye
# <b> p: Your message was '!raw' 'hello goodbye'.
# <p> !raw
# <b> p: Your message was '!raw' ''.
@bot.raw
@bot.command("!raw")
async def raw(self: Bot, user, ran, msg):
    yield f"Your message was '{ran}' '{msg}'.
```
Note how even in raw mode, the part before the first space of the message is not in the message, and is instead accessible in the `ran` parameter.

Also note how the decorators must be applied in reverse order (`@raw` followed by `@command`, or `@add_argument` followed by `@argparse` followed by `@command`). It's easier to think about it if you imagine the decorator having an open bracket at the end, closing at the end of the function. Like this:
```
bot.raw(
	bot.command("!raw")(
		async def ......
	)
)
```

## Colours
Colours are fun! They are supported with the `Format` and `Colour` classes.

## Running commands in parallel
If you have slow or long-running commands, it may be wise to allow running commands in parallel. When you are constructing a `Bot`, use the `max_coros` parameter to change the maximum number of coroutines that will be spawned for commands. Set it to -1 (any number less than or equal to zero works) for no limit, although keep DoS in mind.

**NB:** You will need some way of marking messages so it is clear what message(s) belong to what command. Additionally, many users are accustomed to having queued commands run one after the other in a deterministic order. As such, `max_coros` defaults to 1.

## Licence

   Copyright 2023-2024 TheTechRobo

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
