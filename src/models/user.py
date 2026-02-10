class User:
    def __init__(self, user_id: str, username: str, age: int = None, birthday: str = None):
        self.user_id = user_id
        self.username = username
        self.age = age
        self.birthday = birthday

    def __repr__(self):
        return f"User(user_id={self.user_id}, username={self.username}, age={self.age}, birthday={self.birthday})"

    def update_age(self, new_age: int):
        self.age = new_age

    def update_birthday(self, new_birthday: str):
        self.birthday = new_birthday

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "username": self.username,
            "age": self.age,
            "birthday": self.birthday
        }