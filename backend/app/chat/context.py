from pydantic import BaseModel


class ChatContext(BaseModel):
    user_id: str
    thread_id: str
    knowledge_base_id: str
