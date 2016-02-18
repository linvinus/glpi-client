#!/usr/bin/env python
#-*- coding:utf-8 -*-

#from subprocess import call
import os,subprocess
import json
import syslog
import datetime
import urllib
import ssl
import fcntl, sys

#HOST USER PASSWORD
import myconfig

pid_file = '/run/lock/ticket_speech_sla.pid'
fp = open(pid_file, 'w')
try:
    fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
except IOError:
    # another instance is running
    sys.exit(0)

SYSLOG=1

def splog(s):
    if SYSLOG :
      syslog.syslog(s)
    else:
      print(s)

def jdump(data):
    splog(json.dumps(data,sort_keys=True, indent=4))

class JSonConfig:
  data={}
  def __init__(self, filename):
    self.TMPFILE=filename
    self.data['id']=0
    self.data['last_check']=datetime.datetime.now() 
    self.load()

  def load(self):
    try:
      data_file = open(self.TMPFILE,'r')
      try:    
        data = json.load(data_file)
        if data :
          if data['id'] :
            self.data['id']=data['id']
          if data['last_check'] :
            self.data['last_check']=datetime.datetime.strptime(data['last_check'],'%Y-%m-%d %H:%M:%S')
            #data['last_check']
      except:
        splog("error json.load count")
      finally:
        data_file.close()
    except IOError:
        splog("IOError")

  def save(self):
    #convert to string
    self.data['last_check']=self.data['last_check'].strftime('%Y-%m-%d %H:%M:%S')
    with open(self.TMPFILE, 'w') as data_file:
      json.dump(self.data, data_file)
      data_file.close()

class Ticket:
    datastart=0

    def __init__(self,glpi):
      self.glpi = glpi

    def get_latest_ticket(self,order):
      #limit=1,start=self.datastart {'id':'ASC','date':'ASC'}
        #P={'order[]':['date']}
        #P={'order[]':'date'}
        #{'order[]':'date'},
        data=self.glpi.listTickets({'order['+order+']':'DESC','order[id]':'DESC'},limit=1,start=self.datastart)
        self.datastart+=1;
        #skip deleted
        while data and data[0] and data[0]['is_deleted'] == '1':
          #splog("get new")
          data=self.glpi.listTickets(limit=1,start=self.datastart)
          self.datastart+=1;
          #jdump(data)
          
        if data :
          now = datetime.datetime.now()
          self.day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
          self.day_end   = now.replace(hour=23, minute=59, second=59, microsecond=0)
          #2016-02-08 11:33:01 sting to datetime
          self.data_date=datetime.datetime.strptime(data[0]['date_mod'],'%Y-%m-%d %H:%M:%S')
          
        #~ jdump(data)
        return data
  

class SLA_class:
    HOST=''
    USER=''
    PASSWORD=''
    TMPFILE='/run/shm/data3.json'
    SDPSAY="spd-say -o rhvoice -l ru,en -t female1 -w "
    NOTIFYSEND="notify-send GLPI "
    datastart=0
    new_tickets=[]
    MAX_NEWTICKETS=3
    #2 - glpi 164 - konstantinov 306 - muraviev 163 konev
    skip_users_id_lastupdater=[2,163,164,306]
    def __init__(self,host,user,password):
	self.HOST=host
	self.USER=user
	self.PASSWORD=password

    def __setup_enviroment(self):
        #p = subprocess.Popen('DISPLAY=:0 dbus-launch', shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        p = subprocess.Popen('cat /home/denis/.dbus/session-bus/$(cat /var/lib/dbus/machine-id)-0 | grep -v "^#"', shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        #p = os.system("cat /home/denis/.dbus/session-bus/$(cat /var/lib/dbus/machine-id)-0")
        for var in p.stdout:
          #splog(var)
          sp = var.split('=', 1)
          #splog(sp)
          os.environ[sp[0]] = sp[1][:-1]
        os.environ['XDG_RUNTIME_DIR'] = "/run/user/1000"
        os.environ['DISPLAY'] = ":0"
        os.environ['PULSE_PROP']= 'media.role=phone'

    def say(self,content):
          splog(content)
          os.system(self.NOTIFYSEND+" '"+content+"'")
          #~ os.system(self.SDPSAY+" '"+content+"'" )
          os.system("echo '"+content+"' | grep -o -E '([[:alnum:]\ \!\?\,\.]+)' | RHVoice-client -s Anna+CLB | aplay >/dev/null 2>&1" )



    def __check_SLA(self,force):
      last_check=self.cfg.data['last_check']
      ret_last_check=last_check

      ticket = Ticket(self.glpi);
      data = ticket.get_latest_ticket('date_mod');
      #splog(" oldid="+old_id+" newid="+data[0]['id'])
      #if new ticket
      #self.data_date=datetime.datetime.strptime(data[0]['date_mod'], '%Y-%m-%d %H:%M:%S')
      
      while data and data[0] and ticket.data_date > ticket.day_start and ticket.data_date < ticket.day_end :
          if int(data[0]['status']) < 5 and ( force or last_check< ticket.data_date ) \
            and not (int(data[0]['users_id_lastupdater']) in self.skip_users_id_lastupdater) \
            and not (int(data[0]['id']) in self.new_tickets) :

            ret_last_check=ticket.data_date

            content=""
            displayname=" НЕИЗВЕСТЕН "
            
            data2=self.glpi.getTicket(ticket=data[0]['id'])
            #get followup user displayname and content
            if data2 and data2['followups']:
                content=data2['followups'][0]['content'].encode('utf-8').strip()
                userdata=self.glpi.listUsers(user=int(data2['followups'][0]['users_id']))
            else:
                content=data[0]['content'].encode('utf-8').strip()
                userdata=self.glpi.listUsers(user=int(data[0]['users']['requester'][0]['id']))

            if userdata and userdata[0] :
              displayname=userdata[0]['displayname'].encode('utf-8').strip()


            content=content[:content.find(" ",200)]
            if force :
              content=" НАПОМИНАЮ прочитайте заявку от пользователя "+displayname #+" "+content
            else:
              content="Обновление заявки номер "+str(data[0]['id'])+" от пользователя "+displayname+" "+content
              
            #jdump(data)
            self.say(content)
          
          data_old=data
          data = ticket.get_latest_ticket('date_mod');
          #setup_envireon()
      return ret_last_check

    def __check_NEW(self):

      old_id = self.cfg.data['id']

      ticket = Ticket(self.glpi);
      data = ticket.get_latest_ticket('date');
      count=0
      #splog(" oldid="+old_id+" newid="+data[0]['id'])
      #if new ticket
      new_ticket_c=0

      while data and data[0]:
        if  int(data[0]['id']) > int(old_id) :
          #splog( (data[0]['id']+" requester=" + data[0]['users']['requester'][0]['id']) )
          if data[0]['users'] and  data[0]['users']['requester'] and data[0]['users']['requester'][0] and data[0]['users']['requester'][0]['id']:
            userdata=self.glpi.listUsers(user=int(data[0]['users']['requester'][0]['id']))
          #splog(userdata)
          displayname=" НЕИЗВЕСТЕН "
          if userdata :
            displayname=userdata[0]['displayname'].encode('utf-8').strip()
          content=data[0]['content'].encode('utf-8').strip()
          content=content[:content.find(" ",200)]
          content="Новая заявка номер "+str(data[0]['id'])+" от пользователя "+displayname+" "+content
          self.say(content)
          self.new_tickets.append(int(data[0]['id']))
          self.cfg.data['id']=max( int(self.cfg.data['id']), int(data[0]['id']))
          new_ticket_c += 1
        data = ticket.get_latest_ticket('date');
        count+=1
        if old_id == 0 or count>self.MAX_NEWTICKETS:
            break
      return new_ticket_c


    def run(self):
      self.cfg = JSonConfig(self.TMPFILE);
      
      self.__setup_enviroment()
      
      #from glpi_client.XMLRPCClient import XMLRPCClient
      #glpi = XMLRPCClient('https://10.10.1.38/glpi')

      from glpi_client.RESTClient import RESTClient
      gcontext = ssl.SSLContext(ssl.PROTOCOL_TLSv1)  # Only for gangstar
      self.glpi = RESTClient(self.HOST,gcontext)
      self.glpi.connect(self.USER, self.PASSWORD)


      tcount = self.__check_NEW() #новые сообщения

      if '-f' in sys.argv :
        self.__check_SLA(1) #напоминание

      
      #сохранить время последней проверки  комментариев
      self.cfg.data['last_check']=self.__check_SLA(0) #новые коммантарии
        
      #jdump(self.cfg.data)
      self.cfg.save()
      return tcount


m = SLA_class(HOST,USER,PASSWORD)


if '-G' in sys.argv : #gui mode
    import time
    import gtk
    import glib


    def menu_run(A,B):
      timeout_cb_run()

    icon=gtk.StatusIcon()
    icon.set_from_icon_name(gtk.STOCK_YES)
    menu = menu = gtk.Menu()

    window_item = gtk.MenuItem("GLPI Refresh now")
    window_item.connect("activate", menu_run,"refresh now")
    menu.append(window_item)

    text_item = gtk.MenuItem("")
    menu.append(text_item)
    
    quit_item = gtk.MenuItem("Quit")
    quit_item.connect("activate", gtk.main_quit, "file.quit")
    menu.append(quit_item)
    menu.show_all()
    def icon_clicked(status, button, time):
        menu.popup(None, None, None, button, time)
    icon.connect('popup-menu', icon_clicked)
    #icon.show()
    minutes_count=0


    def timeout_cb_run():
      global minutes_count
      count=0
      
      if minutes_count > 60*2: #every 2 hour
        sys.argv.append("-f")
        count=m.run()
        sys.argv.pop()
        minutes_count=0
      else:
        count=m.run()
      
      if(count > 0):
        icon.set_blinking(True)
        def stop_blinking():
            icon.set_blinking(False)
            return False
        glib.timeout_add_seconds(10,  stop_blinking)

      minutes_count+=1
      text_item.set_label(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
      return True #glib.timeout continue 

    timeout_cb_run()
    glib.timeout_add_seconds(60, timeout_cb_run)
    gtk.main()

elif  '-d' in sys.argv: #continuous run daemon mode
    while True:
      m.run()
      time.sleep(60)
else:                   #one time run
    m.run()
