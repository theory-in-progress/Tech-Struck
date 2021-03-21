import functools
import re
from typing import Dict, Iterable, TypeVar, Union
from urllib import parse

from discord import AllowedMentions, Embed, Member, User
from discord.ext import commands, flags  # type: ignore

_F = TypeVar(
    "_F",
)


class InvalidFieldArgs(commands.CommandError):
    pass


class EmbeyEmbedError(commands.CommandError):
    def __str__(self) -> str:
        return "The embed has no fields/attributes populated"


class InvalidUrl(commands.CommandError):
    def __init__(self, invalid_url: str, *, https_only: bool = False) -> None:
        self.invalid_url = invalid_url
        self.https_only = https_only

    def __str__(self) -> str:
        return "The url entered (`%s`) is invalid.%s" % (
            self.invalid_url,
            "\nThe url must be https" if self.https_only else "",
        )


class InvalidColor(commands.CommandError):
    def __init__(self, value) -> None:
        self.value = value

    def __str__(self):
        return "%s isn't a valid color, eg: `#fff000`, `f0f0f0`" % self.value


class UrlValidator:
    def __init__(self, *, https_only=False) -> None:
        self.https_only = https_only

    def __call__(self, value):
        url = parse.urlparse(value)
        schemes = ("https",) if self.https_only else ("http", "https")
        if url.scheme not in schemes or not url.hostname:
            raise InvalidUrl(value, https_only=self.https_only)
        return value


def colortype(value: str):
    try:
        return int(value.removeprefix("#"), base=16)
    except ValueError:
        raise InvalidColor(value)


url_type = UrlValidator(https_only=True)


def process_message_mentions(message: str) -> str:
    if not message:
        return ""
    for _type, _id in re.findall(r"(role|user):(\d{18})", message):
        message = message.replace(
            _type + ":" + _id, f"<@!{_id}>" if _type == "user" else f"<@&{_id}>"
        )
    for label in ("mention", "ping"):
        for role in ("everyone", "here"):
            message = message.replace(label + ":" + role, f"@{role}")
    return message


class FlagAdder:
    def __init__(self, kwarg_map: Dict[str, Iterable], *, default_mode: bool = False):
        self.kwarg_map = kwarg_map
        self.default_mode = default_mode

    def call(self, func: _F, **kwargs) -> _F:
        if kwargs.pop("all", False):
            for flags in self.kwarg_map.values():
                self.apply(flags=flags, func=func)
            return func
        kwargs = {**{k: self.default_mode for k in self.kwarg_map.keys()}, **kwargs}
        for k, v in kwargs.items():
            if v:
                self.apply(flags=self.kwarg_map[k], func=func)
        return func

    def __call__(self, func=None, **kwargs):
        if func is None:
            return functools.partial(self.call, **kwargs)
        return self.call(func, **kwargs)

    def apply(self, *, flags: Iterable, func: _F) -> _F:
        for flag in flags:
            flag(func)
        return func


embed_input = FlagAdder(
    {
        "basic": (
            flags.add_flag("--title", "-t"),
            flags.add_flag("--description", "-d"),
            flags.add_flag("--fields", "-f", nargs="+"),
            flags.add_flag("--colour", "--color", "-c", type=colortype),
        ),
        "image": (
            flags.add_flag("--thumbnail", "-th", type=url_type),
            flags.add_flag("--image", "-i", type=url_type),
        ),
        "author": (
            flags.add_flag("--authorname", "--aname", "-an"),
            flags.add_flag("--autoauthor", "-aa", action="store_true", default=False),
            flags.add_flag("--authorurl", "--aurl", "-au", type=url_type),
            flags.add_flag("--authoricon", "--aicon", "-ai", type=url_type),
        ),
        "footer": (
            flags.add_flag("--footericon", "-fi", type=url_type),
            flags.add_flag("--footertext", "-ft"),
        ),
    }
)


allowed_mentions_input = FlagAdder(
    {
        "all": (
            flags.add_flag(
                "--everyonemention", "-em", default=False, action="store_true"
            ),
            flags.add_flag("--rolementions", "-rm", default=False, action="store_true"),
            flags.add_flag("--usermentions", "-um", default=True, action="store_false"),
        )
    },
    default_mode=True,
)


def dict_to_embed(data: Dict[str, str], author: Union[User, Member] = None):
    embed = Embed()
    for field in ("title", "description", "colour"):
        if (value := data.pop(field, None)) :
            setattr(embed, field, value)
    for field in "thumbnail", "image":
        if (value := data.pop(field, None)) :
            getattr(embed, "set_" + field)(url=value)

    if data.pop("autoauthor") and author:
        embed.set_author(name=author.display_name, icon_url=str(author.avatar_url))
    if "authorname" in data and data["authorname"]:
        kwargs = {}
        if (icon_url := data.pop("authoricon", None)) :
            kwargs["icon_url"] = icon_url
        if (author_url := data.pop("authorurl", None)) :
            kwargs["url"] = author_url

        embed.set_author(name=data.pop("authorname"), **kwargs)

    if "footertext" in data and data["footertext"]:
        kwargs = {}
        if (footer_icon := data.pop("footericon", None)) :
            kwargs["icon_url"] = footer_icon

        embed.set_footer(text=data.pop("footertext"), **kwargs)

    fields = data.pop("fields") or []
    if len(fields) % 2 == 1:
        raise InvalidFieldArgs(
            "Number of arguments for fields must be an even number, pairs of name and value"
        )

    for name, value in zip(fields[::2], fields[1::2]):
        embed.add_field(name=name, value=value)

    if embed.to_dict() == {"type": "rich"}:
        raise EmbeyEmbedError()

    return embed


def dict_to_allowed_mentions(data):
    return AllowedMentions(
        everyone=data.pop("everyonemention"),
        roles=data.pop("rolementions"),
        users=data.pop("usermentions"),
    )
