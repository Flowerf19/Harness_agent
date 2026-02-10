class Conversation:
    def __init__(self, user_id: str, messages: list = None):
        self.user_id = user_id
        self.messages = messages if messages is not None else []

    def add_message(self, message: str):
        self.messages.append(message)

    def get_history(self) -> list:
        return self.messages

    def clear_history(self):
        self.messages = []

    def __repr__(self):
        return f"<Conversation user_id={self.user_id} messages_count={len(self.messages)}>"