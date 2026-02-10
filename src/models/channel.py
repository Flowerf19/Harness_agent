class Channel:
    def __init__(self, channel_id: str, name: str, type: str):
        self.channel_id = channel_id
        self.name = name
        self.type = type

    def __repr__(self):
        return f"<Channel id={self.channel_id} name={self.name} type={self.type}>"

    def to_dict(self):
        return {
            "channel_id": self.channel_id,
            "name": self.name,
            "type": self.type
        }