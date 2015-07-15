import sys
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy import create_engine
Base = declarative_base()

class User(Base):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    email = Column(String(80), nullable=False)
    picture = Column(String(250))

class Restaurant(Base):
    __tablename__ = 'restaurant'
    name = Column(String(80), nullable=False)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship(User)
    menuItems = relationship('MenuItem', cascade='all, delete-orphan')

    @property
    def serialize(self):
        return {
                'name': self.name,
                'id': self.id
        }


class MenuItem(Base):
    __tablename__ = 'menu_item'
    name = Column(String(80), nullable=False)
    id = Column(Integer, primary_key=True)
    course = Column(String(250))
    description = Column(String(250))
    price = Column(String(8))
    restaurant_id = Column(Integer, ForeignKey('restaurant.id'))
    restaurant = relationship(Restaurant)
    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship(User)

    @property
    def serialize(self):
        """Returns object data in easily serializeable form."""
        return {
                'name': self.name,
                'description': self.description,
                'id': self.id,
                'price': self.price,
                'course': self.course
        }

# end
engine = create_engine('postgres://nqkjjumdijpzme:2Szqv_rdkuk7cUvjgIPXcCQH-A@ec2-54-83-46-91.compute-1.amazonaws.com:5432/d3afm4vspt0ust')
# engine = create_engine('sqlite:///restaurantmenu_withusers.db')
Base.metadata.create_all(engine)
