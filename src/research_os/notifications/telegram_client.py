from __future__ import annotations
import httpx

class TelegramClient:
    def __init__(self, token: str, chat_id: str, timeout: float=10.0):
        self.token=token; self.chat_id=chat_id; self.timeout=timeout
    async def send(self, text: str) -> None:
        url=f"https://api.telegram.org/bot{self.token}/sendMessage"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response=await client.post(url,json={"chat_id":self.chat_id,"text":text})
            response.raise_for_status()
            data=response.json()
            if not data.get("ok"): raise RuntimeError("Telegram API rejected message")
