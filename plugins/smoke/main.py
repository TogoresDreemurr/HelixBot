class Plugin:
    def __init__(self) -> None:
        self._api = None
        self.ping_count = 0

    def on_load(self, api) -> None:
        self._api = api
        api.logger("[smoke] on_load")
        api.register_event("ping", self.on_ping)
        api.register_event("message", self.on_message)

    def on_enable(self) -> None:
        if self._api:
            self._api.logger("[smoke] on_enable")

    def on_disable(self) -> None:
        if self._api:
            self._api.logger("[smoke] on_disable")

    def on_unload(self) -> None:
        if self._api:
            self._api.logger("[smoke] on_unload")

    def on_ping(self, *args, **kwargs) -> None:
        self.ping_count += 1
        if self._api:
            self._api.logger(f"[smoke] ping received (count={self.ping_count})")

    async def on_message(self, message) -> None:
        if message.content == "!ping":
            await message.channel.send("pong")
