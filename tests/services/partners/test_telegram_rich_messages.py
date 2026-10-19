"""Native rich-message delivery, with no network or real bot credentials."""

import json
import re
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from telegram import Bot, ReplyParameters
from telegram.error import BadRequest, EndPointNotFound, Forbidden, TimedOut
from telegram.request import BaseRequest

from deeptutor.partners.bus.events import OutboundMessage
from deeptutor.partners.bus.queue import MessageBus
from deeptutor.partners.channels.telegram import TelegramChannel

MARKDOWN = "# Progress\n\n**Summary**\n\n| Area | Action |\n|---|---|\n| Journal | Save goals |\n\n```python\nprint('**literal**')\n```"


class CaptureRequest(BaseRequest):
    """Exercise real SDK serialization while keeping all requests in memory."""

    def __init__(self):
        self.calls = []

    @property
    def read_timeout(self):
        return 5

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def do_request(self, url, method, request_data=None, **kwargs):
        endpoint = url.rsplit("/", 1)[-1]
        self.calls.append((endpoint, request_data.json_parameters if request_data else {}))
        result = {"message_id": 99}
        if endpoint == "getMe":
            result = {"id": 99, "is_bot": True, "first_name": "Synthetic"}
        return 200, json.dumps({"ok": True, "result": result}).encode()


class RichMessageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.channel = TelegramChannel({"token": "test-token"}, MessageBus())
        self.bot = SimpleNamespace(
            do_api_request=AsyncMock(return_value={"message_id": 99}),
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=99)),
            edit_message_text=AsyncMock(),
            send_message_draft=AsyncMock(),
        )
        self.channel._app = SimpleNamespace(bot=self.bot)

    async def test_public_sdk_serializes_native_payload_without_private_hooks(self):
        request = CaptureRequest()
        async with Bot("123456:SYNTHETIC_TOKEN", request=request) as bot:
            self.channel._app = SimpleNamespace(bot=bot)
            await self.channel._send_text(
                123, MARKDOWN, ReplyParameters(message_id=7), {"message_thread_id": 4}
            )
        endpoint, payload = request.calls[-1]
        self.assertEqual(endpoint, "sendRichMessage")
        self.assertEqual(json.loads(payload["rich_message"]), {"markdown": MARKDOWN})
        self.assertEqual(json.loads(payload["reply_parameters"])["message_id"], 7)
        self.assertEqual(payload["message_thread_id"], "4")

    async def test_final_reply_sends_original_markdown_as_native_rich_message(self):
        reply = ReplyParameters(message_id=7)
        await self.channel._send_text(123, MARKDOWN, reply, {"message_thread_id": 4})
        self.bot.do_api_request.assert_awaited_once_with(
            "sendRichMessage",
            api_kwargs={
                "chat_id": 123,
                "rich_message": {"markdown": MARKDOWN},
                "reply_parameters": reply,
                "message_thread_id": 4,
            },
        )
        self.bot.send_message.assert_not_awaited()

    async def test_normal_send_does_not_cut_a_table_at_4000_characters(self):
        markdown = "| Area | Notes |\n|---|---|\n" + "| A | " + "long note " * 650 + " |"
        await self.channel.send(
            OutboundMessage(channel="telegram", chat_id="123", content=markdown)
        )
        calls = self.bot.do_api_request.await_args_list
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].kwargs["api_kwargs"]["rich_message"]["markdown"], markdown)
        self.bot.send_message_draft.assert_not_awaited()

    async def test_completed_stream_edits_same_message_to_native_rich_format(self):
        await self.channel.send_delta("123", MARKDOWN, {"_stream_id": "s1"})
        await self.channel.send_delta("123", "", {"_stream_id": "s1", "_stream_end": True})
        self.bot.do_api_request.assert_awaited_once_with(
            "editMessageText",
            api_kwargs={"chat_id": 123, "message_id": 99, "rich_message": {"markdown": MARKDOWN}},
        )
        self.assertNotIn("123", self.channel._stream_bufs)

    async def test_long_stream_keeps_preview_bounded_and_final_markdown_whole(self):
        markdown = MARKDOWN + "\n\n" + "x" * 6000
        await self.channel.send_delta("123", markdown, {"_stream_id": "s1"})
        self.assertLessEqual(len(self.bot.send_message.await_args.kwargs["text"]), 4000)
        await self.channel.send_delta("123", "", {"_stream_id": "s1", "_stream_end": True})
        self.assertEqual(
            self.bot.do_api_request.await_args.kwargs["api_kwargs"]["rich_message"]["markdown"],
            markdown,
        )

    async def test_missing_endpoint_falls_back_and_remembers_capability(self):
        self.bot.do_api_request.side_effect = EndPointNotFound("Endpoint not found")
        await self.channel._send_text(123, "**first**")
        await self.channel._send_text(123, "**second**")
        self.assertEqual(self.bot.do_api_request.await_count, 1)
        self.assertEqual(self.bot.send_message.await_count, 2)
        self.assertEqual(self.bot.send_message.await_args.kwargs["text"], "<b>second</b>")

    async def test_format_rejection_falls_back_only_for_this_message(self):
        self.bot.do_api_request.side_effect = [
            BadRequest("can't parse rich message"),
            {"message_id": 100},
        ]
        await self.channel._send_text(123, "**first**")
        await self.channel._send_text(123, "**second**")
        self.assertEqual(self.bot.do_api_request.await_count, 2)
        self.bot.send_message.assert_awaited_once()

    async def test_timeout_and_permission_errors_never_trigger_another_send(self):
        for error in (TimedOut(), Forbidden("Forbidden"), BadRequest("Chat not found")):
            with self.subTest(error=type(error).__name__):
                self.bot.do_api_request.reset_mock(side_effect=True)
                self.bot.do_api_request.side_effect = error
                with self.assertRaises(type(error)):
                    await self.channel._send_text(123, MARKDOWN)
                self.bot.do_api_request.assert_awaited_once()
                self.bot.send_message.assert_not_awaited()

    async def test_rich_edit_not_modified_does_not_create_duplicate(self):
        await self.channel.send_delta("123", MARKDOWN, {"_stream_id": "s1"})
        self.bot.do_api_request.side_effect = BadRequest("Message is not modified")
        await self.channel.send_delta("123", "", {"_stream_id": "s1", "_stream_end": True})
        self.bot.send_message.assert_awaited_once()
        self.bot.edit_message_text.assert_not_awaited()
        self.assertNotIn("123", self.channel._stream_bufs)

    async def test_final_edit_format_fallback_preserves_every_long_reply_word(self):
        async def reject_html(**kwargs):
            if kwargs.get("parse_mode") == "HTML":
                raise BadRequest("Can't parse entities")
            return SimpleNamespace(message_id=99)

        self.bot.send_message.side_effect = reject_html
        self.bot.edit_message_text.side_effect = reject_html
        self.bot.do_api_request.side_effect = BadRequest("Can't parse rich message")
        words = [f"w{i}" for i in range(1800)]
        markdown = MARKDOWN + "\n\n" + " ".join(words)

        await self.channel.send_delta("123", markdown, {"_stream_id": "s1"})
        await self.channel.send_delta("123", "", {"_stream_id": "s1", "_stream_end": True})

        edits = [
            call.kwargs
            for call in self.bot.edit_message_text.await_args_list
            if "parse_mode" not in call.kwargs
        ]
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["message_id"], 99)
        # The first plain send was the preview; only subsequent sends are final chunks.
        extra_chunks = [
            call.kwargs["text"]
            for call in self.bot.send_message.await_args_list
            if "parse_mode" not in call.kwargs
        ][1:]
        self.assertGreaterEqual(len(extra_chunks), 2)
        final_chunks = [edits[0]["text"], *extra_chunks]
        self.assertTrue(all(len(chunk) <= 4000 for chunk in final_chunks))
        self.assertEqual(re.findall(r"w\d+", " ".join(final_chunks)), words)
        self.assertNotIn("123", self.channel._stream_bufs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
