from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    practitioner_id = db.Column(db.String(50), nullable=False)
    phone_number = db.Column(db.String(15), nullable=False)
    emr_system = db.Column(db.String(50), nullable=True)
    emr_url = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f'<Phone No. {self.phone_number}>'

class CallSession(db.Model):
    __tablename__ = "call_session"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(50), nullable=False)
    validated = db.Column(db.Boolean, nullable=True, default=False)
    practitioner_id = db.Column(db.String(50), nullable=True)
    patient_id = db.Column(db.String(50), nullable=True)
    data = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f'<session id: {self.session_id}>'