"""
This plugin is a mapper plugin
"""
import copy
import time
import libs.argp as argp
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf Mapper'
SNAME = 'mapper'
PURPOSE = 'a mapper for aardwolf'
AUTHOR = 'Bast'
VERSION = 1



def dbcreate(sqldb, plugin, **kwargs):
  """
  create the mapper class, this is needed because the Sqldb baseclass
  can be reloaded since it is a plugin
  """

  class Mapperdb(sqldb):
    """
    a class to manage sqlite3 databases
    """
    def __init__(self, plugin, **kwargs):
      """
      initialize the class
      """
      sqldb.__init__(self, plugin, **kwargs)

      self.version = 11

      self.addtable('areas', """CREATE TABLE IF NOT EXISTS areas (
            uid         TEXT    NOT NULL,   -- vnum or how the MUD identifies the area
            name        TEXT,               -- name of area
            texture     TEXT,               -- background area texture
            color       TEXT,               -- ANSI colour code.
            flags       TEXT NOT NULL DEFAULT '',      -- area flags
            UNIQUE (uid)
        );
        CREATE INDEX IF NOT EXISTS areas_uid_index ON areas (uid);
        CREATE INDEX IF NOT EXISTS areas_name_index ON areas (name);
        """, keyfield='uid')

      self.addtable('rooms', """CREATE TABLE IF NOT EXISTS rooms (
            uid           TEXT NOT NULL,   -- vnum or how the MUD identifies the room
            name          TEXT,            -- name of room
            area          TEXT,            -- which area
            building      TEXT,            -- which building it is in
            terrain       TEXT,            -- eg. road OR water
            info          TEXT,            -- eg. shop,healer
            notes         TEXT,            -- player notes
            x             INTEGER,
            y             INTEGER,
            z             INTEGER,
            norecall      INTEGER DEFAULT 0,
            noportal      INTEGER DEFAULT 0,
            ignore_exits_mismatch INTEGER NOT NULL DEFAULT 0,
            UNIQUE (uid),
            FOREIGN KEY(area) REFERENCES areas(uid)
        );
        CREATE INDEX IF NOT EXISTS rooms_info_index ON rooms (info);
        CREATE INDEX IF NOT EXISTS rooms_terrain_index ON rooms (terrain);
        CREATE INDEX IF NOT EXISTS rooms_name_index ON rooms (name);
        CREATE INDEX IF NOT EXISTS rooms_area_index ON rooms (area);
        """, keyfield='uid')

      self.addtable('exits', """CREATE TABLE IF NOT EXISTS exits (
            dir         TEXT    NOT NULL, -- direction, eg. "n", "s"
            fromuid     TEXT    NOT NULL, -- exit from which room
            touid       TEXT    NOT NULL, -- exit to which room
            level       STRING  NOT NULL DEFAULT '0', -- minimum level to make use of this exit
            PRIMARY KEY(fromuid, dir),
            FOREIGN KEY(fromuid) REFERENCES rooms(uid)
          );
        CREATE INDEX IF NOT EXISTS exits_fromuid_index ON exits (fromuid);
        CREATE INDEX IF NOT EXISTS exits_touid_index ON exits (touid);
        """)

      self.addtable('bookmarks', """CREATE TABLE IF NOT EXISTS bookmarks (
          uid         TEXT    NOT NULL,   -- vnum of room
          notes       TEXT,               -- user notes
          UNIQUE (uid)
        );
        """, keyfield='uid')

      self.addtable('storage', """CREATE TABLE IF NOT EXISTS storage (
          name        TEXT NOT NULL,
          data        TEXT NOT NULL,
          PRIMARY KEY (name)
        );
        """, keyfield='name')

      # Need to do this after adding tables
      self.postinit()

    def turnonpragmas(self):
      """
      turn on pragmas for the db
      """
      #-- PRAGMA foreign_keys = ON;
      self.dbconn.execute("PRAGMA foreign_keys=Off;")
      #-- PRAGMA journal_mode=WAL
      self.dbconn.execute("PRAGMA journal_mode=delete;")

    def postinit(self):
      """
      this is run after the __init__ function
      """
      sqldb.postinit(self)

      self.dbconn.executescript("""
        BEGIN TRANSACTION;
        DROP TABLE IF EXISTS rooms_lookup;
        CREATE VIRTUAL TABLE rooms_lookup USING FTS3(uid, name);
        INSERT INTO rooms_lookup (uid, name) SELECT uid, name FROM rooms;
        COMMIT;
        """)

    def updatearea(self, areainfo):
      """
      update an area
      """
      narea = copy.deepcopy(dict(areainfo))
      if 'texture' not in narea:
        narea['texture'] = ''
      #for i in narea:
        #narea[i] = self.fixsql(str(narea[i]))
      self.api('libs.io:send:msg')('data: %s' % narea)
      cur = self.dbconn.cursor()
      stmt = self.converttoinsert('areas', replace=True)
      self.api('libs.io:send:msg')('stmt: %s' % stmt)
      cur.execute(stmt, narea)
      self.dbconn.commit()
      cur.close()

    def getarea(self, areaname):
      """
      get a area
      """
      area = None

      stmt = 'SELECT * from areas where uid = %s' % self.fixsql(areaname)
      tstuff = self.select(stmt)
      if len(tstuff) > 0:
        area = tstuff[0]

      return area

    def setnorecall(self, value, room):
      """
      set a room to norecall
      """
      stmt = "UPDATE ROOMS set norecall = %s where uid = %s" % (value, room)
      self.modify(stmt)

    def setnoportal(self, value, room):
      """
      set a room to noportal
      """
      stmt = "UPDATE ROOMS set noportal = %s where uid = %s" % (value, room)
      self.modify(stmt)

    def getroom(self, uid):
      """
      get a room
      """
      room = None

      stmt = 'SELECT * from rooms where uid = %s' % uid
      tstuff = self.select(stmt)
      if len(tstuff) == 1:
        room = tstuff[0]
      elif len(tstuff) == 0:
        self.api('libs.io:send:msg')('no room for %s' % uid)
      elif len(tstuff) > 1:
        self.api('libs.io:send:msg')('more than one room for %s' % uid)

      if room:
        room['uid'] = str(room['uid'])

        room['exits'] = {}
        room['exitlocks'] = {}
        stmt = 'SELECT * from exits where fromuid = %s' % uid
        exits = self.select(stmt)
        for i in exits:
          room['exits'][i['dir']] = str(i['touid'])
          room['exitlocks'][i['dir']] = int(i['level'])

      return room

    def roomsearch(self, search, exact=False, area=None):
      """
      search for rooms
      """
      tstr = "LIKE"
      if exact:
        tstr = "="
      stmt = "SELECT * FROM rooms WHERE name %s %s" % (
          tstr,
          self.fixsql(search, like=not exact))

      if area:
        stmt = stmt + " AND area = %s" % self.fixsql(area)

      return self.select(stmt)

    def saveroom(self, roomd):
      """
      save into the rooms table
      """
      #roomd['name'] = self.fixsql(roomd['name'])
      if 'notes' not in roomd:
        roomd['notes'] = ""
      if not 'noportal' not in roomd:
        roomd['noportal'] = 0
      if not 'norecall' not in roomd:
        roomd['norecall'] = 0
      if not 'ignore_exits_mismatch' not in roomd:
        roomd['ignore_exits_mismatch'] = 0

      stmt = self.converttoinsert('rooms', replace=True)
      self.api('libs.io:send:msg')('saveroom stmt: %s' % stmt)

      self.modify(stmt, roomd)

    def saveexits(self, room):
      """
      save into the exits table
      """
      exits = []
      for i in room['exits'].keys():
        exits.append({'fromuid':room['uid'], 'touid':room['exits'][i],
                      'dir':i, 'level':0})

      stmt = self.converttoinsert('exits', replace=True)
      self.api('libs.io:send:msg')('saveexits stmt: %s' % stmt)

      self.modifymany(stmt, exits)

    def savegmcproom(self, roominfo):
      """
      update a room
      """
      roomd = copy.deepcopy(roominfo)

      self.api('libs.io:send:msg')('savegmcproom: %s' % roomd)

      self.api('libs.io:send:msg')('saving room %s' % roomd['uid'])
      self.saveroom(roomd)
      self.saveexits(roomd)
      self.api('libs.io:send:msg')('saved room %s' % roomd['uid'])

    def purgeroom(self, uid):
      """
      purge a room
      """

      stmt = "DELETE FROM exits WHERE touid = %s;" % uid
      stmt = stmt + "DELETE FROM rooms_lookup WHERE uid = %s;" % uid
      stmt = stmt + "DELETE FROM bookmarks WHERE uid = %s;" % uid
      stmt = stmt + "DELETE FROM rooms WHERE uid = %s;" % uid

      self.modifyscript(stmt)


  return Mapperdb(plugin, **kwargs)


class Plugin(AardwolfBasePlugin):
  """
  a plugin to monitor aardwolf events
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)

    self.api('dependency:add')('core.sqldb')

    self.mapperdb = None
    self.current_room = None
    self.addflag = {}
    self.rooms = {}
    self.areas = {}

    self.currentspeedwalk = False

    self.lastsearch = []
    self.lastdest = None

    self.bounce_portal = None
    self.bounce_recall = None

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('setting:add')('maxdepth', 300, int,
                            'max depth to search')

    self.api('core.log:toggle:to:console')(self.plugin_id)
    self.api('core.log:toggle:to:client')(self.plugin_id)

    self.mapperdb = dbcreate(self.api('sqldb.baseclass')(), self,
                             dbname='mapper', dbdir=self.save_directory)

    self.api('libs.io:send:msg')('mapperdb: %s' % self.mapperdb)

    self.api('setting:add')('shownotes', True, bool,
                            'show notes when entering a room')

    parser = argp.ArgumentParser(add_help=False,
                                 description='show mapper information for a room')
    parser.add_argument('room', help='the room number',
                        default=None, nargs='?', type=int)
    self.api('core.commands:command:add')('showroom', self.cmd_showroom,
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='purge a room')
    parser.add_argument('room', help='the room number',
                        default=None, nargs='?', type=int)
    self.api('core.commands:command:add')('purgeroom', self.cmd_purgeroom,
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='lookup a room')
    parser.add_argument('room', help='a string',
                        default=None, nargs='?')
    parser.add_argument('-e', "--exact", help="the argument is the exact name",
                        action="store_true")
    self.api('core.commands:command:add')('find', self.cmd_find,
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='lookup a room in a specific area')
    parser.add_argument('room', help='a string',
                        default=None, nargs='?')
    parser.add_argument('area', help='a string',
                        default=None, nargs='?')
    parser.add_argument('-e', "--exact", help="the argument is the exact name",
                        action="store_true")
    self.api('core.commands:command:add')('area', self.cmd_area,
                                          parser=parser)

    parser = argp.ArgumentParser(
        add_help=False,
        description='goto the next room from the previous search result')
    self.api('core.commands:command:add')('next', self.cmd_next,
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='resume going to a room')
    self.api('core.commands:command:add')('resume', self.cmd_resume,
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='goto a room')
    parser.add_argument('room', help='the room number',
                        default=None, nargs='?', type=int)
    self.api('core.commands:command:add')('goto', self.cmd_goto,
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='walk to room (no portals)')
    parser.add_argument('room', help='the room number',
                        default=None, nargs='?', type=int)
    self.api('core.commands:command:add')('walk', self.cmd_walk,
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='get speedwalk for a path')
    parser.add_argument('start', help='the room number',
                        default=None, nargs='?', type=int)
    parser.add_argument('end', help='the room number',
                        default=None, nargs='?', type=int)
    self.api('core.commands:command:add')('spw', self.cmd_speedwalk,
                                          parser=parser)

    self.api('core.triggers:trigger:add')('noportal',
                                          r"^Magic walls bounce you back\.$")
    self.api('core.triggers:trigger:add')('norecall',
                                          r"^You cannot (recall|return home) from this room\.")

    ## backup the db every 4 hours
    #self.api('core.timers:add:timer')('mapper_backup', self.backupdb,
                                #60*60*4, time='0000')

    #self.api('setting:add')('backupstart', '0000', 'miltime',
                      #'the time for a db backup, like 1200 or 2000')
    #self.api('setting:add')('backupinterval', '4h', 'timelength',
                      #'the interval to backup the db, default every 4 hours')
    #self.api('core.events:register:to:event')('map_backupstart', self.changetimer)
    #self.api('core.events:register:to:event')('map_backupinternval', self.changetimer)

    self.api('core.events:register:to:event')('trigger_noportal', self.noportal)
    self.api('core.events:register:to:event')('trigger_norecall', self.norecall)

    self.api('core.events:register:to:event')('GMCP:room.area', self.updatearea)
    self.api('core.events:register:to:event')('GMCP:room.info', self.updateroom)

  def comparerooms(self, room1, room2):
    """
    compare two rooms
    """
    keystocomp = ['name', 'terrain', 'exits',
                  'x', 'y', 'z', 'uid', 'info', 'area']

    for key in keystocomp:
      if isinstance(room1[key], dict):
        for i in room1[key].keys():
          if i in room2[key]:
            if room1[key][i] != room2[key][i]:
              self.api('libs.io:send:msg')('did not match on %s:%s' % (key, i))
              return False

      else:
        if room1[key] != room2[key]:
          self.api('libs.io:send:msg')('did not match on %s' % key)
          return False

    return True

  def changetimer(self, _=None):
    """
    do something when the reportminutes changes
    """
    self.api('core.timers:remove:timer')('mapper_backup')
    self.api('core.timers:add:timer')('mapper_backup',
                                      self.backupdb,
                                      self.api('setting:get')('backupinterval'),
                                      time=self.api('setting:get')('backupstart'))

  def backupdb(self):
    """
    backup the db from the timer
    """
    tstr = time.strftime('%a-%b-%d-%Y-%H-%M', time.localtime())
    if self.mapperdb:
      self.mapperdb.backupdb(tstr)

  def uninitialize(self, _=None):
    """
    handle uninitializing
    """
    AardwolfBasePlugin.uninitialize(self)
    self.mapperdb.close()

  def noportal(self, _=None):
    """
    add a noportal flag to a room
    """
    if self.api('aflags.check')('blindness'):
      self.api('libs.io:send:client')("You are affected by blindness, " \
                               "room %s will not be set as noportal" % self.current_room)
      return
    if self.current_room != None and self.current_room in self.rooms and \
        self.rooms[self.current_room] != None and \
        self.rooms[self.current_room]['noportal'] != 1:
      self.mapperdb.setnoportal(1, self.current_room)
      self.cacheroom(self.current_room, force=True)
      self.api('libs.io:send:client')('Marking room %s as noportal' % self.current_room)

  def norecall(self, _=None):
    """
    add a norecall flag to a room
    """
    if self.api('aflags.check')('blindness'):
      self.api('libs.io:send:client')("You are affected by blindness, " \
                               "room %s will not be set as noportal" % self.current_room)
      return
    if self.current_room != None and self.current_room in self.rooms and \
        self.rooms[self.current_room] != None and \
        self.rooms[self.current_room]['norecall'] != 1:
      self.mapperdb.setnorecall(1, self.current_room)
      self.cacheroom(self.current_room, force=True)
      self.api('libs.io:send:client')('Marking room %s as norecall' % self.current_room)

  def updatearea(self, args):
    """
    update the area from GMCP:room.area
    """
    self.api('libs.io:send:msg')('room.area: %s' % args)
    area = args['data']
    area['color'] = area['col']
    area['uid'] = area['id']
    self.mapperdb.updatearea(args['data'])
    self.api('net.GMCP:sendpacket')("request room")

  def cacheroom(self, roomnum, force=False):
    """
    add a room to the cache if it is in the database
    """
    roomnum = str(roomnum)
    if roomnum not in self.rooms or force:
      room = self.mapperdb.getroom(roomnum)
      if room:
        self.rooms[roomnum] = room
        return True

    return False

  def updateroom(self, args):
    """
    update a room
    """
    roominfo = args['data']
    if not roominfo['num'] or roominfo['num'] == -1:
      return

    #-- Try to accomodate closed clan rooms and other nomap rooms.
    #-- We'll have to make some other changes elsewhere as well.
    #if roominfo['num'] == -1:
      #roominfo['num'] = "nomap_"..roominfo['name'].."_".. roominfo['area']

    self.current_room = str(roominfo['num'])

    if not(roominfo['zone'] in self.areas) or not self.areas[roominfo['zone']]:
      area = self.mapperdb.getarea(roominfo['zone'])
      if not area:
        self.api('net.GMCP:sendpacket')('request area')
      else:
        self.areas[area['uid']] = area

    dbroom = {}
    dbroom['uid'] = str(roominfo['num'])
    dbroom['name'] = roominfo['name']
    dbroom['area'] = roominfo['zone']
    dbroom['building'] = 0
    dbroom['terrain'] = roominfo['terrain']
    dbroom['info'] = roominfo['details']
    dbroom['x'] = roominfo['coord']['x']
    dbroom['y'] = roominfo['coord']['y']
    dbroom['z'] = 0
    dbroom['exits'] = {}
    for i in roominfo['exits']:
      dbroom['exits'][i] = str(roominfo['exits'][i])

    cachedroom = None
    self.api('libs.io:send:msg')('uid in room: %s' % (dbroom['uid'] in self.rooms))
    self.cacheroom(dbroom['uid'])

    if not dbroom['uid'] in self.rooms:
      self.mapperdb.savegmcproom(dbroom)
      self.cacheroom(dbroom['uid'])

    try:
      cachedroom = self.rooms[dbroom['uid']]
    except KeyError:
      self.api('libs.io:send:traceback')('Did not cache room: %s' % dbroom['uid'])

    if not cachedroom['ignore_exits_mismatch'] and \
       not self.comparerooms(dbroom, cachedroom):
      self.api('libs.io:send:msg')('cachedroom: %s' % cachedroom)
      self.api('libs.io:send:msg')('dbroom: %s' % dbroom)
      msg = []
      msg.append('@r---------------------------@w')
      if dbroom['area'] != cachedroom['area']:
        msg.append('@RThis room has changed areas@w')
        msg.append('@Rpurge area %s with purgearea if this area has been replaced@w' % \
                      cachedroom['area'])
        msg.append('@ROtherwise, purge this room with purgeroom@w')
      else:
        msg.append('@RThis room has changed@w')
        msg.append('@Rpurge this room with purgeroom@w')
      msg.append('@r---------------------------@w')
      self.api('libs.io:send:client')(msg)
      return

    room = cachedroom

    if self.api('setting:get')('shownotes') and room and \
              room['notes']:
      divider = '@R' + self.api('core.utils:center:colored:string')('Room Notes', '-', 60) + '@w'

      self.api('libs.io:send:client')(divider)
      self.api('libs.io:send:client')(room['notes'])
      self.api('libs.io:send:client')('@R' + 60 * '-' + '@w')

  def cmd_showroom(self, args):
    """
    show info for a room
    """
    msg = []

    if not args['room']:
      roomnum = self.api('net.GMCP:value:get')('room.info.num')
    else:
      roomnum = args['room']

    self.api('libs.io:send:msg')('roomnum: %s' % roomnum)

    if not roomnum:
      return True, ["Don't know what room we are in"]

    roomnum = str(roomnum)

    if roomnum not in self.rooms:
      self.rooms[roomnum] = self.mapperdb.getroom(roomnum)

    room = self.rooms[roomnum]

    if not room:
      msg.append('Room %s is not in the database' % roomnum)
    else:
      msg.append('Current Room')
      msg.append('-------------------------------------')
      msg.append('%-15s : %s' % ('Room Name', room['name']))
      msg.append('%-15s : %s' % ('ID', room['uid']))
      msg.append('%-15s : %s' % ('Area', room['area']))
      msg.append('%-15s : %s' % ('Terrain', room['terrain']))
      msg.append('%-15s : %s' % ('Info', room['info']))
      msg.append('%-15s : %s' % ('Notes', room['notes']))
      flags = []
      if room['noportal'] == 1:
        flags.append("noportal")
      if room['norecall'] == 1:
        flags.append("norecall")
      msg.append('%-15s : %s' % ('Flags', ", ".join(flags)))
      msg.append('%-15s : %s' % ('Room Name', room['name']))

      if room['exits']:
        msg.append('-------------------------------------')
        msg.append('Exits')
        for i in room['exits'].keys():
          msg.append('  %-10s : %s' % (i, room['exits'][i]))

      msg.append('%15s : %s' % ('Ignore Exits Mismatch',
                                room['ignore_exits_mismatch']))

    return True, msg

  def cmd_purgeroom(self, args):
    """
    purge a room
    """
    if not args['room']:
      roomnum = self.api('net.GMCP:value:get')('room.info.num')
    else:
      roomnum = args['room']

    roomnum = str(roomnum)

    self.mapperdb.purgeroom(roomnum)
    del self.rooms[roomnum]

    return True, ["Room %s was purged from the database" % roomnum]

  def cmd_find(self, args):
    """
    find a room
    """
    msg = []
    tdata = self.mapperdb.roomsearch(str(args['room']), args['exact'])

    data = sorted(tdata, key=lambda x: x['area'])

    if data:
      self.lastsearch = data
      for room in data:
        msg.append("%-12s %-10s %-s" % (room['area'], room['uid'],
                                        room['name']))

    else:
      msg.append("No rooms match the search arguments")

    return True, msg

  def cmd_area(self, args):
    """
    find a room in an area
    """
    msg = []

    area = args['area']

    if not area:
      area = self.api('net.GMCP:value:get')('room.info.zone')

    tdata = self.mapperdb.roomsearch(str(args['room']), args['exact'], area)

    data = sorted(tdata, key=lambda x: x['area'])

    if data:
      self.lastsearch = data
      for room in data:
        msg.append("%-12s %-10s %-s" % (room['area'], room['uid'],
                                        room['name']))

    else:
      msg.append("No rooms match the search arguments")

    return True, msg

  def cmd_next(self, _=None):
    """
    go to the next room in the search list
    """
    msg = []
    if len(self.lastsearch) > 0:
      self.lastdest = self.lastsearch.pop(0)
      self.gotoroom(self.lastdest['uid'])

      return True, []
    else:
      msg.append('There are no more rooms in the search results')

    return True, msg

  def cmd_resume(self, _=None):
    """
    resume moving to the last room
    """
    if self.lastdest:
      self.gotoroom(self.lastdest['uid'])

      return True, []

    return True, ['There is not a destination to resume']

  def cmd_goto(self, args):
    """
    goto a room
    """
    if args['room']:
      self.gotoroom(str(args['room']))

    return True, []

  def cmd_walk(self, args):
    """
    walk to a room (no portals)
    """
    if args['room']:
      self.gotoroom(str(args['room']), walk=True)

    return True, []

  def cmd_speedwalk(self, args):
    """
    get a speedwalk between two rooms

    #bp.mapper.spw 26151 32418
    #bp.mapper.spw 32418 32421
    """
    start = args['start']
    end = args['end']

    if not start:
      return False, ['Please specify a start room']

    if not end:
      return False, ['Please specify an end room']

    path, reason, depth = self.findpath(str(start), str(end))

    if path:
      spwlk = self.converttospeedwalk(path)
      return True, [spwlk]

    return True, [reason, '%s' % path, str(depth)]

  def gotoroom(self, uid, start=None, walk=False):
    """
    goto a room
    """
    try:
      uid = int(uid)
    except ValueError:
      self.api('libs.io:send:client')('gotoroom: passed a non-numerical uid')
      return

    uid = str(uid)

    if uid not in self.rooms:
      self.cacheroom(uid)

    if uid not in self.rooms:
      self.api('libs.io:send:client')('gotoroom: %s is not in the database' % uid)
      return

    room = self.rooms[uid]

    self.api('libs.io:send:client')('Going to room %s (%s)' % (
        room['name'], room['uid']))

    if self.currentspeedwalk:
      self.api('libs.io:send:client')(
          'Already in a speedwalk, will abort this speedwalk')
      return

    if not start:
      start = self.api('net.GMCP:value:get')('room.info.num')

    if not start:
      self.api('libs.io:send:client')(
          'Cannot do pathfinding because start room is not known. Try "look"')
      return

    rooms, reason, depth = self.findpath(start, uid)

  def findpath(self, start, end, noportals=False, norecalls=False):
    """
    find a path between two rooms
    """
    start = str(start)
    end = str(end)

    charlevel = self.api('net.GMCP:value:get')('char.status.level')
    chartier = self.api('net.GMCP:value:get')('char.base.tier')

    if not chartier:
      chartier = 0
    if not charlevel:
      charlevel = 201

    if not start or start == 'None':
      start = self.api('net.GMCP:value:get')('room.info.num')

    if start not in self.rooms:
      if not self.cacheroom(start):
        self.api('libs.io:send:msg')('findpath: start: %s is not in the database' % start)
        return {}, 'start room not in database', 0

    #if not(end in self.rooms):
      #if not(self.cacheroom(end)):
        #self.api('libs.io:send:msg')('findpath: end: %s is not in the database' % uid)
        #return {}

    walkone = None

    for direction in self.rooms[start]['exits']:
      dest = self.rooms[start]['exits'][direction]
      levellock = self.rooms[start]['exitlocks'][direction]
      if str(dest) == str(end) and levellock <= charlevel and \
            ((walkone is None) or (len(direction) > len(walkone))):
        # if one room away, walk there (don't portal), but prefer a cexit
        walkone = direction

    if walkone != None:
      return {'dir':walkone, 'uid':end}, 'walkone', 1

    depth = 0
    maxdepth = self.api('setting:get')('maxdepth')

    room_sets = {}
    rooms_list = []
    found = False
    ftd = {}
    somevar = ""
    next_room = 0

    if start == end:
      return {}, 'start == end', 0

    if not start:
      return {}, 'no start room', 0

    if not end:
      return {}, 'no end room', 0

    rooms_list.append(self.mapperdb.fixsql(end))

    visited = []

    if noportals:
      visited.append(self.mapperdb.fixsql("*"))
    if norecalls:
      visited.append(self.mapperdb.fixsql("**"))

    while not found and depth < maxdepth:
      depth = depth + 1

      if depth > 1:
        rooms_list = []
        if (depth - 1) in room_sets:
          ftd = room_sets[depth - 1]
        else:
          ftd = {}

        for i in ftd:
          fromuid = self.mapperdb.fixsql(ftd[i]['fromuid'])
          if fromuid not in rooms_list:
            rooms_list.append(fromuid)

      # prune the search space
      for i in rooms_list:
        if i not in visited:
          visited.append(i)

      # get all exits to any room in the previous set
      # ordering by length(dir) ensures that custom exits (always longer than 1 char) get
      # used preferentially to normal ones (1 char)
      sqlstr = "select fromuid, touid, dir from exits where touid in (%s) " \
          "and fromuid not in (%s) and ((fromuid not in ('*','**') and " \
          "level <= %s) or (fromuid in ('*','**') and level <= %s)) "\
          "order by length(dir) asc" % \
            (",".join(rooms_list),
             ",".join(visited),
             charlevel,
             charlevel + (chartier * 10))

      if depth < 10:
        print sqlstr

      dcount = 0
      room_sets[depth] = {}

      for row in self.mapperdb.select(sqlstr):

        dcount = dcount + 1

        room_sets[depth][row['fromuid']] = {'fromuid':row['fromuid'],
                                            'touid':row['touid'], 'dir':row['dir']}
        #if row['fromuid'] == "*" or (row['fromuid'] == "**" and f != "*" \
              #and f != start) or row['fromuid'] == start:
        if row['fromuid'] == start:
          final = row['fromuid']
          found = True
          found_depth = len(room_sets)

      if dcount == 0:
        print 'found', found
        return {}, 'dcount no paths', 0

    if depth == maxdepth and not found:
      return {}, 'depth == maxdepth', maxdepth

    if found is False:
      return {}, 'found no paths', 0

    path = []

    print 'found_depth: %s' % found_depth
    print 'room_sets: %s' % room_sets

    ftd = room_sets[found_depth][final]

    if (final == "*" and self.rooms[start]['noportal'] == 1) or \
          (final == "**" and self.rooms[start]['norecall'] == 1):
      if self.rooms[start].norecall != 1 and self.bounce_recall != None:
        path.append(self.bounce_recall)
        if end == self.bounce_recall:
          return path, 'bouncerecall path found', found_depth

      elif self.rooms[start]['noportal'] != 1 and self.bounce_portal != None:
        path.append(self.bounce_portal)
        if end == self.bounce_portal:
          return path, 'bounceportal path found', found_depth

      else:
        jump_room, path_type = self.findNearestJumpRoom(start, end, somevar)
        if not jump_room:
          return {}, 'jump no paths', 0

        # this could be optimized away by building the path in
        #findNearestJumpRoom, but the gain would be negligible
        path, code, first_depth = self.findpath(start, jump_room, True, True)
        if bit.band(path_type, 1) != 0:
          # path_type 1 means just walk to the destination
          return path, 'path found', first_depth

        second_path, code, second_depth = self.findpath(jump_room, end)
        for i in second_path:
          path.append(second_path[i]) # bug on this line if path is nil?

        return path, 'second found path', first_depth + second_depth

    print 'ftd: %s' % ftd
    path.append({'dir':ftd['dir'], 'uid':ftd['touid']})

    next_room = ftd['touid']
    while depth > 1:
      depth = depth - 1
      ftd = room_sets[depth][next_room]
      next_room = ftd['touid']
      path.append({'dir':ftd['dir'], 'uid':ftd['touid']})

    return path, 'path found', found_depth

  def converttospeedwalk(self, path):
    """
    convert a path to a speedwalk
    """
    spw = []
    for room in path:
      if len(spw) == 0:
        spw.append({'dir':room['dir'], 'num':1})
      else:
        if room['dir'] == spw[-1]['dir']:
          spw[-1]['num'] = spw[-1]['num'] + 1
        else:
          spw.append({'dir':room['dir'], 'num':1})

    spws = ''
    for direction in spw:
      if direction['num'] > 1:
        spws = spws + '%d%s' % (direction['num'], direction['dir'])
      else:
        spws = spws + direction['dir']

    return spws

  # Very similar to findpath, but looks forwards instead of backwards (so only walks)
  # and stops at the nearest portalable or recallable room
  def findNearestJumpRoom(self, src, dst, target_type):
    """
    find the nearest Jump Room
    """
    depth = 0
    max_depth = self.api('setting:get')('maxdepth')
    room_sets = {}
    rooms_list = []
    found = False
    ftd = {}
    destination = ""
    next_room = 0
    visited = []
    path_type = ""

    charlevel = self.api('net.GMCP:value:get')('char.status.level')
    chartier = self.api('net.GMCP:value:get')('char.base.tier')

    if not chartier:
      chartier = 0
    if not charlevel:
      charlevel = 201

    rooms_list.append(self.mapperdb.fixsql(src))

    while not found and depth < max_depth:
      depth = depth + 1

      for i in rooms_list:
        if i not in visited:
          visited.append(i)

      sqlstr = "select fromuid, touid, dir, norecall, noportal " \
            "from exits,rooms where rooms.uid = exits.touid " \
            "and exits.fromuid in (%s) and exits.touid " \
            "not in (%s) and exits.level <= %s " \
            "order by length(exits.dir) asc" % \
                  (",".join(rooms_list), visited, charlevel)
      dcount = 0
      for row in self.mapperdb.select(sqlstr):
        dcount = dcount + 1
        rooms_list.append(self.mapperdb.fixsql(row['touid']))
        if ((self.bounce_portal != None or target_type == "*") \
            and row['noportal'] != 1) \
            or ((self.bounce_recall != None \
            or target_type == "**") \
            and row['norecall'] != 1) \
            or row['touid'] == dst:
          path_type = ((row['touid'] == dst) & 1)|( (((row['noportal'] == 1) & 2)|0) + (((row['norecall'] == 1) & 4)|0) )
          # path_type 1 means walking to the destination is closer than bouncing
          # path_type 2 means the bounce room allows recalling but not portalling
          # path_type 4 means the bounce room allows portalling but not recalling
          # path_type 0 means the bounce room allows both portalling and recalling
          destination = row['touid']
          found = True
          found_depth = depth

      if dcount == 0:
        return "", path_type, found_depth

    if found is False:
      return "", -1, -1

    return destination, path_type, found_depth
