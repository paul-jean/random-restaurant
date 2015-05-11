from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from database_setup import Restaurant, MenuItem

# init Flask
app = Flask(__name__)

# init SQLAlchemy
Base = declarative_base()
engine = create_engine('sqlite:///restaurantmenu.db')
Base.metadata.bind = engine
DBSession = sessionmaker(bind = engine)
session = DBSession()

# Stub data before setting up db:
# Fake Restaurants
restaurant = {'name': 'The CRUDdy Crab', 'id': '1'}
restaurants = [{'name': 'The CRUDdy Crab', 'id': '1'}, {'name':'Blue Burgers',
'id':'2'},{'name':'Taco Hut', 'id':'3'}]
# Fake Menu Items
items = [ {'name':'Cheese Pizza', 'description':'made with fresh cheese',
'price':'$5.99','course' :'Entree', 'id':'1'}, {'name':'Chocolate\
Cake','description':'made with Dutch Chocolate', 'price':'$3.99',
'course':'Dessert','id':'2'},{'name':'Caesar Salad', 'description':'with fresh\
    organic vegetables','price':'$5.99',
    'course':'Entree','id':'3'},{'name':'Iced Tea', 'description':'with\
        lemon','price':'$.99', 'course':'Beverage','id':'4'},{'name':'Spinach\
        Dip', 'description':'creamy dip with fresh spinach','price':'$1.99',
        'course':'Appetizer','id':'5'} ]
item =  {'name':'Cheese Pizza','description':'made with fresh\
                cheese','price':'$5.99','course' :'Entree'}

@app.route('/')
@app.route('/restaurants/')
def showRestaurants():
    return render_template('restaurants.html', restaurants=restaurants)

@app.route('/restaurant/new')
def newRestaurant():
    return render_template('newRestaurant.html')

@app.route('/restaurant/<int:rest_id>/edit')
def editRestaurant(rest_id):
    # rest = restaurants[0]
    for r in restaurants:
        if int(r['id']) == rest_id:
            rest = r
            break
    return render_template('editRestaurant.html', rest=rest)

@app.route('/restaurant/<int:rest_id>/delete')
def deleteRestaurant(rest_id):
    return render_template('deleteRestaurant.html', rest_id=rest_id)

@app.route('/restaurant/<int:rest_id>/')
@app.route('/restaurant/<int:rest_id>/menu')
def showMenu(rest_id):
    return render_template('placeholder.html', message='This page is the menu for \
    restaurant %s.' % rest_id)

@app.route('/restaurant/<int:rest_id>/menu/new')
def newMenuItem(rest_id):
    return render_template('placeholder.html', message='This page is for \
    making a new menu item for restaurant %s.' % rest_id)

@app.route('/restaurant/<int:rest_id>/menu/<int:menu_id>/edit')
def editMenuItem(rest_id, menu_id):
    return render_template('placeholder.html', message='This page is for \
    editing menu item %s for restaurant %s.' % (menu_id, rest_id))

@app.route('/restaurant/<int:rest_id>/menu/<int:menu_id>/delete')
def deleteMenuItem(rest_id, menu_id):
    return render_template('placeholder.html', message='This page is for \
    deleting menu item %s for restaurant %s.' % (menu_id, rest_id))

if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host = '0.0.0.0', port = 5000)
