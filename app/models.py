from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum, Boolean
from sqlalchemy.orm import relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index = True)
    email = Column(String(255), unique = True, index=True, nullable = False)
    name = Column(String(255), nullable = True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default = datetime.utcnow)
    
    # Relationship : one to many slack connections
    slack_connections = relationship("SlackConnection", back_populates="user")
    
    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"
    
class SlackConnection(Base):
    __tablename__ = "slack_connections"
    
    id = Column(Integer, primary_key=True, index = True)
    
    # Foreign Key : user id
    user_id = Column(Integer, ForeignKey("users.id"),nullable = False)
    
    # Slack workspace 
    slack_team_id = Column(String(64), index = True, nullable = False)
    slack_team_name = Column(String(255), nullable = True)
    
    # Bot access token used to call slack web api
    bot_access_token = Column(Text, nullable = True)
    
    # Scopes and metadata
    scope = Column(Text, nullable = True)
    authed_user_id = Column(String(64), nullable = True)
    
    # status & timestamps
    status = Column(String(32), default = "active", index = True)
    installed_at = Column(DateTime, default = datetime.utcnow)
    updated_at = Column(DateTime, default = datetime.utcnow, onupdate = datetime.utcnow)
    
    #  Relationship : back to user
    
    user = relationship("User", back_populates="slack_connections")
    
    def __repr__(self):
        return (
            f"<SlackConnection id={self.id} user_id = {self.user_id} "
            f"team = {self.slack_team_name} ({self.slack_team_id}) status = {self.status}>"
        )
    
    
    
class OAuthState(Base):
    __tablename__ = "oauth_states"
    
    id = Column(Integer, primary_key=True, index = True)
    provider = Column(String(32), nullable = False)
    state = Column(String(128), unique = True, index = True, nullable = False)
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable = False)
    used = Column(Boolean, default = False, nullable = False)
    
    created_at = Column(DateTime, default = datetime.utcnow, nullable = False)
    expires_at = Column(DateTime, nullable = False)
    
    user = relationship("User")
    
    