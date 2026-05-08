from sqlalchemy import Column, String, ForeignKey, Text
from database import Base

class Chat(Base):
    __tablename__ = "chats"
    id = Column(String, primary_key=True)
    title = Column(String)
    user_id = Column(String)


class Message(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True)
    chat_id = Column(String, ForeignKey("chats.id"))
    role = Column(String)
    content = Column(Text)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(String, primary_key=True)
    chat_id = Column(String, ForeignKey("chats.id"), index=True)
    filename = Column(String)
    content = Column(Text)


class ImageAttachment(Base):
    __tablename__ = "image_attachments"
    id = Column(String, primary_key=True)
    chat_id = Column(String, ForeignKey("chats.id"), index=True)
    filename = Column(String)
    path = Column(String)


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, index=True)   # ✅ changed
    password = Column(String)
