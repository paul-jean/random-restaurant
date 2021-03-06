"""
Random Noms: a simple web app to organize restaurants and menus.

Provides create, read, update, and delete (CRUD) operations for
restaurants and their menu items. The main app page lets the user
obtain a randomly chosen restaurant (randomly chosen "noms")
from the database.

User must log in using social sign-on (FB or G+) to perform CRUD
operations. Authentication and authorization done using a hybrid auth
flow proceeding in several token exchanges. A one-time code is sent
from the auth API to the client, relayed to the app server, and back
to the auth API. After the one-time code round-trip, the auth API
provides a long-lived access token to the app server for making
API requests on behalf of the user.

Implemented using the Flask framework, Postgres, and the SQLAlchemy database ORM.

Created as an assignment in the Udacity Full Stack Nanodegree program.

Author: Paul-Jean Letourneau
Date: August 2015
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from database_setup import Restaurant, MenuItem, User
from bleach import clean
from random import randrange
from re import sub
from flask import session as login_session
import random, string
from db_link import getDBLink
from functools import wraps
from urlparse import urlparse
from dict2xml import dict2xml as xmlify
from flask import Response

from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

# init Flask
app = Flask(__name__)

CLIENT_ID = json.loads(open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Random Noms"

# init SQLAlchemy
Base = declarative_base()
dblink = getDBLink()
engine = create_engine(dblink)
Base.metadata.bind = engine

DBSession = sessionmaker(bind = engine)
session = DBSession()

def createUser(login_session):
    """
    Creates a new user.

    Args:
        login_session: session dict, containing username, email, picture, etc

    Returns:
        The newly created user id.
    """
    newUser = User(
            name = login_session['username'],
            email = login_session['email'],
            picture = login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email = login_session['email']).one()
    return user.id

def getUserInfo(user_id):
    """
    Get profile info for a user.

    Args:
        user_id: user id integer

    Returns:
        The user object.
    """
    user = session.query(User).filter_by(id = user_id).one()
    return user

def getUserID(user_email):
    """
    Get user's id from their email address.

    Args:
        user_email: user's email address

    Returns:
        The user id.
    """
    try:
        user = session.query(User).filter_by(email = user_email).one()
        return user.id
    except:
        return None

@app.route('/login/')
def showLogin():
    """ Show the login page. """
    state = ''.join(random.choice(string.ascii_uppercase + string.digits) for x in xrange(32))
    client_id = json.loads(open('client_secrets.json', 'r').read())['web']['client_id']
    login_session['state'] = state
    return render_template('login.html', STATE = state, G_CLIENT_ID = client_id, login_session = login_session)

@app.route('/disconnect')
def disconnect():
    """ Disconnect from social sign-on. """
    if 'provider' in login_session:
        if login_session['provider'] == 'google':
            gdisconnect()
        if login_session['provider'] == 'facebook':
            fbdisconnect()
        del login_session['provider']
        flash('You have been successfully logged out.')
        return redirect(url_for('showRestaurants'))
    else:
        flash('You were not logged in.')
        return redirect(url_for('showRestaurants'))


@app.route('/gdisconnect')
def gdisconnect():
    """ Disconnect from G+ social sign-on. """
    # Only disconnect a connected user:
    credentials = login_session.get('credentials')
    if credentials is None:
        response = make_response(json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Send http GET request to revoke current token:
    access_token = credentials.access_token
    url = ('https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token)
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]

    if result['status'] == '200':
        # Reset the user's session:
        del login_session['credentials']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']

        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        # For some reason, the given token was invalid:
        response = make_response(json.dumps('Failed to revoke token for given user.'), 400)
        response.headers['Content-Type'] = 'application/json'
        return response

@app.route('/fbdisconnect')
def fbdisconnect():
    """ Disconnect from FB social sign-on. """
    fb_id = login_session['facebook_id']
    access_token = login_session['access_token']
    url = 'https://graph.facebook.com/%s/permissions?fb_exchange_token=%s' % (fb_id, access_token)
    h = httplib2.Http()
    # Remove the access token for this user from FB's server:
    result = h.request(url, 'DELETE')[1]
    # Remove the user's login session:
    del login_session['username']
    del login_session['email']
    del login_session['picture']
    del login_session['user_id']
    del login_session['facebook_id']
    return 'you have been logged out'

@app.route('/gconnect', methods = ['POST'])
def gconnect():
    """ Sign in to G+. """
    # Verify the page's state token to be sure it was generated by this app server
    if request.args.get('state') != login_session['state']:
        # If the state token is invalid, stop and return an error
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain the one-time authorization code returned from the G+ API gateway
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(json.dumps('Failed to upgrade authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s' % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'

    # Verify that the access token is used for the intended user
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app
    if result['issued_to'] != CLIENT_ID:
        response = make_response(json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's"
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later user
    login_session['credentials'] = credentials
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params = params)

    data = answer.json()

    login_session['provider'] = 'google'
    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    # Check if this user has an account
    user_id = getUserID(login_session['email'])
    if not user_id:
        # Create a new user
        user_id = createUser(login_session)

    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % login_session['username'])
    return output

@app.route('/fbconnect', methods = ['POST'])
def fbconnect():
    """ Sign in to FB. """
    # Verify the page's state token to be sure it was generated by this app server
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Obtain one-time code sent from FB authentication:
    access_token = request.data
    print "access token received %s " % access_token

    # Exchange one-time code for long-lived access token via OAuth:
    app_id = json.loads(open('fb_client_secrets.json', 'r').read())['web']['app_id']
    app_secret = json.loads(open('fb_client_secrets.json', 'r').read())['web']['app_secret']
    url = 'https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=%s&client_secret=%s&fb_exchange_token=%s' % (app_id, app_secret, access_token)

    # https://code.google.com/p/httplib2/issues/detail?id=303
    httplib2.debuglevel = 4

    h = httplib2.Http()
    result = h.request(url, 'GET')[1]

    # Strip the expire tag from the token:
    token = result.split('&')[0]

    # Use the token to get user info from the FB API:
    url = 'https://graph.facebook.com/v2.4/me?%s&fields=id,name,email' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    user_data = json.loads(result)

    login_session['provider'] = 'facebook'
    login_session['username'] = user_data['name']
    login_session['email'] = user_data['email']
    login_session['facebook_id'] = user_data['id']

    stored_token = token.split("=")[1]
    login_session['access_token'] = stored_token

    # Need a separate API call to get user's profile pic:
    url = 'https://graph.facebook.com/v2.2/me/picture?%s&redirect=0&height=200&width=200' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)
    login_session['picture'] = data['data']['url']

    # Check if this user is already registered:
    user_id = getUserID(login_session['email'])
    if not user_id:
        # If not, create an id for them:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % login_session['username'])
    return output

@app.route('/about/')
def about():
    """ Show the about page. """
    return render_template('about.html', login_session = login_session)

def login_required(f):
    """
    Decorator to restrict access to users who are logged in.

    Args:
        f: input function

    Returns:
        Redirects to the login page if the user is not logged in.
        Otherwise executes the given function.
    """
    @wraps(f)
    def login_wrapped(*args, **kwargs):
        if 'username' not in login_session:
            return redirect(url_for('showLogin'))
        return f(*args, **kwargs)
    return login_wrapped

@app.route('/restaurants/')
def showRestaurants():
    """
        List all restaurants.
        For users not signed in, show public restaurant page with no edit features.
    """
    restaurants = session.query(Restaurant)
    if 'username' not in login_session:
        return render_template('restaurants_public.html', restaurants = restaurants, login_session = login_session)
    return render_template('restaurants.html', restaurants = restaurants, login_session = login_session)

@app.route('/restaurants/JSON/')
def showRestaurantsJSON():
    """ List all restaurants in JSON format. """
    restaurants = session.query(Restaurant).all()
    return jsonify(Restaurants = [r.serialize for r in restaurants])

@app.route('/restaurants/XML/')
def showRestaurantsXML():
    """ List all restaurants in XML format. """
    restaurants = session.query(Restaurant).all()
    rs = {'restaurant': [r.serialize for r in restaurants]}
    return Response(xmlify(rs, wrap = 'Restaurants'), mimetype = 'text/xml')

def getRandomRestaurant():
    """ Get a random restaurant from the database. """
    restaurants = session.query(Restaurant).all()
    num_restaurants = len(restaurants)
    rand_restaurant_index = randrange(0, num_restaurants)
    rand_restaurant = restaurants[rand_restaurant_index]
    return rand_restaurant

@app.route('/random_restaurant/JSON/')
def randomRestaurantJSON():
    """ Get a random restaurant in JSON format. """
    rand_restaurant = getRandomRestaurant()
    return jsonify(rand_restaurant.serialize)

@app.route('/random_restaurant/XML/')
def randomRestaurantXML():
    """ Get a random restaurant in XML format. """
    rand_restaurant = getRandomRestaurant()
    d = { 'restaurant': rand_restaurant.serialize }
    return Response(xmlify(d, wrap = 'RandomRestaurant'), mimetype = 'text/xml')

@app.route('/')
@app.route('/random/', methods = ['GET'])
def randomRestaurant():
    """ Get a randomly chosen restaurant. """
    return render_template('random_button.html', login_session = login_session)

def isValidUrl(urlString):
    """
    Verify a url is valid.

    Args:
        urlString: url to verify

    Returns:
        True if the url is valid, False otherwise.
    """
    urlDict = urlparse(urlString)
    if urlDict.netloc == '' or urlDict.path == '':
        return False
    return True

def isValidInput(inputString):
    """
    Verify a form input is valid.

    Args:
        inputString: form input to verify

    Returns:
        True if the input is valid, False otherwise.
    """
    if len(inputString) == 0:
        return False
    return True

@app.route('/restaurant/new', methods = ['GET', 'POST'])
@login_required
def newRestaurant():
    """ Create a new restaurant. """
    if request.method == 'POST':
        restName = request.form['name']
        restName = clean(restName)
        if not isValidInput(restName):
            flash('Restaurant name is required')
            return redirect(url_for('showRestaurants'))
        restObj = Restaurant(name = restName, user_id = login_session['user_id'])
        session.add(restObj)
        session.commit()
        restaurants = session.query(Restaurant)
        flash('Added restaurant: ' + restName)
        return redirect(url_for('showRestaurants'))
    else:
        return render_template('newRestaurant.html', login_session = login_session)

@app.route('/restaurant/<int:rest_id>/edit', methods = ['GET', 'POST'])
@login_required
def editRestaurant(rest_id):
    """
    Edit a restaurant.

    Args:
        rest_id: restaurant id

    Returns:
        Renders the restaurant page.
    """
    restObj = session.query(Restaurant).filter_by(id = rest_id).one()
    if restObj.user_id != login_session['user_id']:
        flash('You are not authorized to edit this restaurant.')
        return redirect(url_for('showRestaurants'))
    if request.method == 'POST':
        restName = request.form['name']
        restName = clean(restName)
        if not isValidInput(restName):
            flash('Restaurant name is required')
            return redirect(url_for('showRestaurants'))
        restObj.name = restName
        session.add(restObj)
        session.commit()
        restaurants = session.query(Restaurant)
        flash('Edited restaurant: ' + restName)
        return redirect(url_for('showRestaurants'))
    else:
        return render_template('editRestaurant.html', restaurant = restObj, login_session = login_session)

@app.route('/restaurant/<int:rest_id>/delete', methods = ['GET', 'POST'])
@login_required
def deleteRestaurant(rest_id):
    """
    Delete a restaurant.

    Args:
        rest_id: restaurant id

    Returns:
        Renders the delete restaurant page.
    """
    restObj = session.query(Restaurant).filter_by(id = rest_id).one()
    if restObj.user_id != login_session['user_id']:
        flash('You are not authorized to delete this restaurant.')
        return redirect(url_for('showRestaurants'))
    if request.method == 'POST':
        session.delete(restObj)
        session.commit()
        flash('Deleted restaurant: ' + restObj.name)
        return redirect(url_for('showRestaurants'))
    else:
        rest = session.query(Restaurant).filter_by(id = rest_id).one()
        return render_template('deleteRestaurant.html', restaurant = rest, login_session = login_session)

@app.route('/restaurant/<int:rest_id>/')
@app.route('/restaurant/<int:rest_id>/menu')
def showMenu(rest_id):
    """
    List all menu items for a restaurant.
    For users not logged in, show the public menu with no edit features.

    Args:
        rest_id: restaurant id

    Returns:
        Renders the restaurant's menu page.
    """
    restObj = session.query(Restaurant).filter_by(id = rest_id).one()
    menuItems = session.query(MenuItem).filter_by(restaurant_id = rest_id).all()
    for i in menuItems:
        i.price = sub('\$', '', i.price)
    if 'user_id' in login_session and restObj.user_id == login_session['user_id']:
        return render_template('menu.html', restaurant = restObj, items = menuItems, login_session = login_session)
    else:
        creator = getUserInfo(restObj.user_id)
        return render_template('menu_public.html', restaurant = restObj, items = menuItems, creator = creator, login_session = login_session)

@app.route('/restaurant/<int:rest_id>/menu/JSON/')
def showMenuJSON(rest_id):
    """
    List all menu items for a restaurant in JSON format.

    Args:
        rest_id: restaurant id

    Returns:
        Restaurant menu in JSON format.
    """
    menuItems = session.query(MenuItem).filter_by(restaurant_id = rest_id).all()
    for i in menuItems:
        i.price = sub('\$', '', i.price)
    return jsonify(MenuItems = [i.serialize for i in menuItems])

@app.route('/restaurant/<int:rest_id>/menu/XML/')
def showMenuXML(rest_id):
    """
    List all menu items for a restaurant in XML format.

    Args:
        rest_id: restaurant id

    Returns:
        Restaurant menu in XML format.
    """
    menuItems = session.query(MenuItem).filter_by(restaurant_id = rest_id).all()
    for i in menuItems:
        i.price = sub('\$', '', i.price)
    ms = { 'menu_item': [m.serialize for m in menuItems] }
    return Response(xmlify(ms, wrap = 'MenuItems'), mimetype = 'text/xml')

@app.route('/restaurant/<int:rest_id>/menu/<int:menu_id>/JSON/')
def showMenuItemJSON(rest_id, menu_id):
    """
    List properties of a menu item in JSON format.

    Args:
        rest_id: restaurant id
        menu_id: menu id

    Returns:
        Menu item in JSON format.
    """
    menuItem = session.query(MenuItem).filter_by(restaurant_id = rest_id, id = menu_id).one()
    menuItem.price = sub('\$', '', menuItem.price)
    return jsonify(MenuItem = menuItem.serialize)

@app.route('/restaurant/<int:rest_id>/menu/<int:menu_id>/XML/')
def showMenuItemXML(rest_id, menu_id):
    """
    List properties of a menu item in XML format.

    Args:
        rest_id: restaurant id
        menu_id: menu id

    Returns:
        Menu item in XML format.
    """
    menuItem = session.query(MenuItem).filter_by(restaurant_id = rest_id, id = menu_id).one()
    menuItem.price = sub('\$', '', menuItem.price)
    m = { 'menu_item': menuItem.serialize }
    return Response(xmlify(m, wrap = 'MenuItem'), mimetype = 'text/xml')

@app.route('/restaurant/<int:rest_id>/menu/new', methods = ['GET', 'POST'])
@login_required
def newMenuItem(rest_id):
    """
    Create a new menu item.

    Args:
        rest_id: restaurant id

    Returns:
        Renders the menu item creation page.
    """
    restObj = session.query(Restaurant).filter_by(id = rest_id).one()
    if restObj.user_id != login_session['user_id']:
        flash('You are not authorized to modify this menu.')
        return redirect(url_for('showMenu', rest_id = rest_id))
    if request.method == 'POST':
        name = clean(request.form['name'])
        if not isValidInput(name):
            flash('Item name is required')
            return redirect(url_for('showMenu', rest_id = rest_id))
        description = clean(request.form['description'])
        if not isValidInput(description):
            flash('Item description is required')
            return redirect(url_for('showMenu', rest_id = rest_id))
        price = clean(request.form['price'])
        if not isValidInput(price):
            flash('Item price is required')
            return redirect(url_for('showMenu', rest_id = rest_id))
        course = clean(request.form['course'])
        picture = clean(request.form['picture'])
        if not isValidUrl(picture):
            picture = None
        newItem = MenuItem(
                name = name, course = course,
                description = description, price = price, picture = picture,
                restaurant_id = rest_id, user_id = restObj.user_id)
        session.add(newItem)
        session.commit()
        flash('Added menu item: ' + name)
        return redirect(url_for('showMenu', rest_id = restObj.id))
    else:
        return render_template('newMenuItem.html', restaurant = restObj, login_session = login_session)

@app.route('/restaurant/<int:rest_id>/menu/<int:menu_id>/edit', methods = ['GET', 'POST'])
@login_required
def editMenuItem(rest_id, menu_id):
    """
    Edit a menu item.

    Args:
        rest_id: restaurant id
        menu_id: menu id

    Returns:
        Renders the menu item edit page.
    """
    menuItemObj = session.query(MenuItem).filter_by(id = menu_id).one()
    restObj = session.query(Restaurant).filter_by(id = rest_id).one()
    if restObj.user_id != login_session['user_id']:
        flash('You are not authorized to edit this menu item.')
        return redirect(url_for('showMenu', rest_id = rest_id))
    if request.method == 'POST':
        name = clean(request.form['name'])
        if not isValidInput(name):
            flash('Item name is required')
            return redirect(url_for('showMenu', rest_id = rest_id))
        description = clean(request.form['description'])
        if not isValidInput(description):
            flash('Item description is required')
            return redirect(url_for('showMenu', rest_id = rest_id))
        price = clean(request.form['price'])
        if not isValidInput(price):
            flash('Item price is required')
            return redirect(url_for('showMenu', rest_id = rest_id))
        picture = clean(request.form['picture'])
        if not isValidUrl(picture):
            picture = None
        course = clean(request.form['course'])
        menuItemObj.name = name
        menuItemObj.description = description
        menuItemObj.price = price
        menuItemObj.picture = picture
        menuItemObj.course = course
        session.add(menuItemObj)
        session.commit()
        flash('Edited menu item: ' + menuItemObj.name)
        menuItems = session.query(MenuItem).filter_by(restaurant_id = rest_id).all()
        return redirect(url_for('showMenu', rest_id = rest_id))
    else:
        return render_template('editMenuItem.html', restaurant = restObj, item = menuItemObj, login_session = login_session)

@app.route('/restaurant/<int:rest_id>/menu/<int:menu_id>/delete', methods = ['GET', 'POST'])
@login_required
def deleteMenuItem(rest_id, menu_id):
    """
    Delete a menu item.

    Args:
        rest_id: restaurant id
        menu_id: menu id

    Returns:
        Renders the delete menu item page.
    """
    menuItemObj = session.query(MenuItem).filter_by(id = menu_id).one()
    restObj = session.query(Restaurant).filter_by(id = rest_id).one()
    if restObj.user_id != login_session['user_id']:
        flash('You are not authorized to delete this menu item.')
        return redirect(url_for('showMenu', rest_id = rest_id))
    if request.method == 'POST':
        session.delete(menuItemObj)
        session.commit()
        flash('Deleted menu item: ' + menuItemObj.name)
        return redirect(url_for('showMenu', rest_id = rest_id))
    else:
        return render_template('deleteMenuItem.html', restaurant = restObj, item = menuItemObj, login_session = login_session)

if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host = '0.0.0.0', port = 5000)
