from app.models.user import User

# Now that all models are imported, we can set up the relationships
from sqlalchemy.orm import relationship

# Add the relationship to User model after all models are defined
User.topics = relationship("Topic", back_populates="creator")