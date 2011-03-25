import os
import urllib2
import string
import re
import logging
from google.appengine.api import urlfetch
from google.appengine.ext.webapp import template
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.ext.webapp.util import run_wsgi_app
from HTMLParser import HTMLParser
from datetime import datetime, timedelta

## Class to hold the calendar and users in the DB
class Calendar(db.Model):
  ICS = db.TextProperty()
  dt = db.DateTimeProperty(auto_now=True)
      
  def date(self):
    return (self.dt + timedelta(hours = 2)).ctime()

class UserPref(db.Model):

  user = db.UserProperty()
  uid = db.StringProperty()
  cal = db.ReferenceProperty()
  query = db.StringProperty()
  nbw = db.IntegerProperty()
    
  @staticmethod
  def getdata(u):
    q = db.GqlQuery("SELECT * FROM UserPref WHERE user = :1", u)
    return q.get()
      
  
## Parser for the data

class infoParser(HTMLParser):
  def __init__(self):
    self.result = []
    self.nbrow = 0
    self.active = 0
    self.finished = 0
    self.skipping=0
    self.current_row = []
    self.current_data = []
    HTMLParser.__init__(self)
    
  def start_table(self, attributes):
    # print "begin table"
    if not self.finished:
      self.active=1
  def end_table(self):
    # print "end table"
    self.active=0
    self.finished=1
    
  def start_tr(self,attributes):
    # print "  begin tr"
    if self.active and not self.skipping:
      self.current_row = []
      
  def end_tr(self):
    # print "  end tr"
    if self.active and not self.skipping:
      self.result.append(self.current_row)
      
  def start_td(self,attributes):
    # print "    begin td"
    if self.active and not self.skipping:
      self.current_data = []
      
  def end_td(self):
    # print "    end td"
    if self.active and not self.skipping:
      self.current_row.append(
        string.join(self.current_data))
        
  def handle_data(self, data):
    if self.active and not self.skipping:
      # print "      datafound:"
      # print data
      # print "      end of data"
      self.current_data.append(data)
    
  def handle_starttag(self, tag, attrs):
    # print "Encountered the beginning of a %s tag" % tag
    if tag == "table":
      self.start_table(attrs)
    elif tag == "tr":
      self.start_tr(attrs)
    elif tag == "td":
      self.start_td(attrs)

  def handle_endtag(self, tag):
    # print "Encountered the end of a %s tag" % tag
    if tag == "table":
      self.end_table()
    elif tag == "tr":
      self.end_tr()
    elif tag == "td":
      self.end_td()

## Parser to get the number of the current week
class weekParser(HTMLParser):
  def __init__(self):
    self.pianoSelected = False
    self.nweek = 1
    HTMLParser.__init__(self)
  
  def handle_starttag(self, tag, attrs):
    if tag == "div" and len(attrs) > 0 and attrs[0][1] == "pianoselected":
      self.pianoSelected = True
    elif tag == "map" and len(attrs) > 0 and self.pianoSelected:
      self.nweek = int(re.sub("[\D]","",attrs[0][1]))
      
  def handle_endtag(self, tag):
    if tag == "div" and self.pianoSelected:
      self.pianoSelected = False
    

def dateICal(date):
  return date.strftime("%Y%m%dT%H%M%S")
  
## Build the ICS
def make_event_list(parsed):
  events = []
  for i in parsed:
    if len(i) < 7:
      continue
    start = datetime.strptime("%s %s" % (i[0], i[1]), "%d/%m/%Y %Hh%M")
    if re.match("^\d{1,2}h$", i[2]):
      delta = datetime.strptime(i[2], "%Hh")
    else: # /2h30min/
      delta = datetime.strptime(i[2], "%Hh%Mmin")
    end = start + timedelta(hours = delta.hour, minutes = delta.minute)

    event = {"groups": i[4],
      "prof": i[5],
      "room": i[6],
      "name": i[3],
      "start": dateICal(start),
      "end": dateICal(end)
      }
      
    event_condensed_name = "%s-%s" % (event["name"], event["prof"])
    event_condensed_name = re.sub('[^\w]','_', event_condensed_name)
    event["uid"] = "%s-%s-%s" % (event["groups"], event["start"], event_condensed_name)
    
    events.append(event)

#   print ""
#    print "UID:chronos-%s-%s-%s" % (event["groups"], dateICal(event["start"]), event_condensed_name)
#    print "DTSTAMP:%s" % dateICal(datetime.now())
#    print "SUMMARY:%s - %s %s" % (event["name"], event["prof"], event["room"])
#    print "DESCRIPTION:Cours: %s\\nProf: %s\\nSalle: %s\\nGroupes: %s" % (event["name"], event["prof"], event["room"], event["groups"])
#    print "DTSTART:%s" % dateICal(event["start"])
#    print "DTEND:%s" % dateICal(event["end"])
#    print "LOCATION:%s" % event["room"]
  return events
    
## Fetch the data from Chronos
def getICS(cal, query, nbw):
    url = "http://chronos.epita.net/"
    url = "http://chronos.epita.net/ade/standard/gui/interface.jsp?projectId=4&login=student&password="

    session_id = ""
    result = urlfetch.fetch(url)
    if result.status_code == 200:
      session_id = result.headers['set-cookie']

    url = "http://chronos.epita.net/ade/standard/gui/interface.jsp?projectId=4&login=student&password="
    result = urlfetch.fetch(url, headers = { 'Cookie': session_id })
    #DisplaySav51 = result.headers['set-cookie']

    tree = "http://chronos.epita.net/ade/standard/gui/tree.jsp"
    #cookie = "%s; %s" % (DisplaySav51, session_id)
    cookie = session_id

    # Find the leaf following the given path
    """categorie = "category=%s" % "trainee"
    url = "%s?%s&expand=false&forceLoad=false&reload=false" % (tree, categorie)
    result = urlfetch.fetch(url, headers = { 'cookie': cookie })

    index_epita = 1
    branch = "branchId=%i" % index_epita
    url = "%s?%s&expand=false&forceLoad=false&reload=false" % (tree, branch)
    result = urlfetch.fetch(url, headers = { 'cookie': cookie })

    branch = "branchId=%i" % 748
    url = "%s?%s&expand=false&forceLoad=false&reload=false" % (tree, branch)

    result = urlfetch.fetch(url, headers = { 'cookie': cookie })

    branch = "branchId=%i" % 989
    url = "%s?%s&expand=false&forceLoad=false&reload=false" % (tree, branch)
    result = urlfetch.fetch(url, headers = { 'cookie': cookie })
    
    # Access the leaf
    select = "selectId=%i" % 1089

    url = "%s?%s&forceLoad=false&scroll=0" % (tree, select)
    result = urlfetch.fetch(url, headers = { 'cookie': cookie })"""

    url = "%s?nbFilters=1&what0=name&how0=contains&filterValue0=%s" % (tree, query)
    result = urlfetch.fetch(url, headers = { 'cookie': cookie })
    
    # Get the time bar
    url = "http://chronos.epita.net/ade/custom/modules/plannings/pianoWeeks.jsp"
    result = urlfetch.fetch(url, headers = { 'cookie': cookie })
    
    parser = weekParser()
    parser.feed(result.content)
    parser.close()
    nweek = parser.nweek - 1
    
    # Set the weeks
    bounds = "http://chronos.epita.net/ade/custom/modules/plannings/bounds.jsp"

    ## Obtain next 8 weeks of the calendar
    week = "week=%i" % nweek
    url = "%s?%s&reset=true" % (bounds, week)
    result = urlfetch.fetch(url, headers = { 'cookie': cookie })
    
    for i in range(1, nbw - 1):
      week = "week=%i" % (nweek + i)
      url = "%s?%s&reset=false" % (bounds, week)
      result = urlfetch.fetch(url, headers = { 'cookie': cookie })
     
    # Retrieve the content and parse it
    info = "http://chronos.epita.net/ade/custom/modules/plannings/info.jsp"
    url = info
    result = urlfetch.fetch(url, headers = { 'cookie': cookie })

    parser = infoParser()
    parser.feed(unicode(result.content, "utf-8", "ignore"))
    parser.close()
    
    # result:
    # parser.result[*][0]: start date
    # after: start hour, length, cours, groups, professor, room
    
    events = make_event_list(parser.result)
    
    template_values = {
      'status': result.status_code,
      'header': result.headers,
      'content': string.replace(result.content,'<','_'),
      'parseres': parser.result,
      'events': events,
      'stamp': dateICal(datetime.now()),
      'id': session_id
    }

    path = os.path.join(os.path.dirname(__file__), 'calendar.ics')
    
    cal.ICS = template.render(path, template_values)
    cal.put()

class GetAll(webapp.RequestHandler):
  def get(self):  
    ups = UserPref.all()
    for up in ups:
        getICS(up.cal, up.query, up.nbw)

## ics of user_id
class ShowICS(webapp.RequestHandler):
  def get(self):
    uid = self.request.get('uid')
  
    if uid:
        q = db.GqlQuery("SELECT * FROM UserPref WHERE uid = :1", uid)
        user = q.get()
        self.response.out.write(user.cal.ICS)
    else:
        self.redirect("/")

## Register ##
class Register(webapp.RequestHandler):
  def get(self):
    user = users.get_current_user()
    query = self.request.get('query')
    nbw = self.request.get('nbw')
    
    ud = UserPref.getdata(user);
    
    if (query == "" or nbw == "") and not ud:
      self.response.out.write("""
        <html>
          <body>
            <h2>Register</h2>
            <form action="/user/register" method="get">
              <div>Search query&nbsp;<input type="text" name="query" size="10"></input></div>
              <div>Number of weeks&nbsp;<input type="text" name="nbw" size="3"></input></div>
              <div><input type="submit" value="Register"></div>
            </form>
          </body>
        </html>""")
    else:
      if not ud:
        up = UserPref()
        up.user = user
        up.uid = user.user_id()
        up.query = query
        up.nbw = int(nbw)
        cal = Calendar()
        getICS(cal, up.query, up.nbw)
        up.cal = cal
        up.put()
        self.redirect("/")
      else:
        self.redirect("/")

## Refresh
class Refresh(webapp.RequestHandler):
  def get(self):
    
    user = users.get_current_user()
    ud = UserPref.getdata(user)
  
    if ud:
      getICS(ud.cal, ud.query, ud.nbw)
      self.redirect("/")
    else:
      self.redirect("/user/register")    

## MainPage    
class MainPage(webapp.RequestHandler):
  def get(self):
  
    user = users.get_current_user()
    ud = UserPref.getdata(user)
  
    if ud:
        template_values = {
          'email': user.email(),
          'updated' : ud.cal.date(),
          'uid' : user.user_id()
        }

        path = os.path.join(os.path.dirname(__file__), 'view.html')
        self.response.out.write(template.render(path, template_values))
    else:
        self.redirect("/user/register")

application = webapp.WSGIApplication([('/', MainPage),
                                      ('/ics', ShowICS),
                                      ('/update', GetAll),
                                      ('/user/register', Register),
                                      ('/user/refresh', Refresh)],
                                      debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
  
