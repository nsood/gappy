#coding=utf-8  
from flask import Flask, request, render_template, make_response, session, redirect, jsonify
import json
#import sqlite3
import time
from flask_cors import CORS
import os, ConfigParser
import re
import telnetlib
import time
import ssl

outer="goto_outer"
inner="goto_inner"
arbiter="goto_arbiter"
promt='GLCNS'

app = Flask(__name__)
CORS(app)

##################### tools function ###################

# 从请求中获取指定数据
def req_get(key):
    ret = request.args.get(key)
    if (ret is None):
        ret = request.form.get(key)
    return ret

# 从会话中获取指定数据
def session_get(key):
        return session.get(key)

# 为会话分配指定数据
def session_set(key, value):
    session[key] = value
    if (value is None):
        session.pop(key)

# 全局数据库函数，select返回对应的数组，update/delete返回受到影响的行数/ROWID
db = None
def db_exec(sql, args=[], lastid=False):
    try:
        global db
        if (db is None):
            db = sqlite3.connect('gappy.db')

        cur = db.execute(sql, args)
        id = cur.lastrowid
        cnt = cur.rowcount
        rs = cur.fetchall()
        cur.close()

        if (sql.startswith('select ')):
            return rs

        if (lastid):
            return id

        return cnt

    except Exception,e:
        #print 'db execute failed\n\tsql: {0}\n\terror: {1}\n\n'.format(sql, e)
        return None

# 数据库初始化
def db_init():
    ret = db_exec('create table users(id integer primary key autoincrement, name varchar)')
  
# 把字符串里多余的空格、前后空格、前后换行全部移除
def strtrim(s):
    s = s.strip(' \n')
    while True:
        n1 = len(s)
        s = s.replace('  ', ' ')
        n2 = len(s)
        if (n1 == n2):
            return s

# 把VTY状态转为对象：'vty-result=2|Not found' -> {'status': 0, 'message': '2|Not
# found'}
def vtyresul_to_obj(s):
    s = strtrim(s)
    if (s[0:11] != 'vty-result='):
        return None
    
    s = s[11:]
    fields = s.split('|')
    if (len(fields) != 2):
        return None

    retobj = {'status':1, 'message':'ok'}
    if (int(fields[0]) == 0):
        return retobj

    retobj['status'] = 0
    retobj['message'] = s
    return retobj

class DictObj(object):
    def __init__(self,map):
        self.map = map

    def __setattr__(self, name, value):
        if name == 'map':
             object.__setattr__(self, name, value)
             return;
        print 'set attr called ',name,value
        self.map[name] = value

    def __getattr__(self,name):
        v = self.map[name]
        if isinstance(v,(dict)):
            return DictObj(v)
        if isinstance(v, (list)):
            r = []
            for i in v:
                r.append(DictObj(i))
            return r                      
        else:
            return self.map[name];

    def __getitem__(self,name):
        return self.map[name]
def jstrtoobj(s):
    dictobj = json.loads(s)
    return DictObj(dictobj)

class Util_telnet(object):
    """description of class"""
    def __init__(self, promt, host='127.0.0.1', port=2601):
        self.promt= promt
        self.host = host
        self.port = port
        self.tn = telnetlib.Telnet()

    def ssl_cmd(self,type,cmd):
        print 'ssl_cmd in'
        rt = {}
        try:
            self.tn.open(self.host, self.port, 1)
        except Exception as e:
            print e
            return rt
        print "open success"
        if (type=="inner"):
            type="goto_inner"
        elif (type=="outer"):
            type="goto_outer"
        elif (type=="arbiter"):
            type="goto_arbiter"
        else:
            type=None
        if (type is None):
            return type
        self.tn.read_until(self.promt+'>', 5)
        self.tn.write('enable\r')
        self.tn.read_until(self.promt+'#', 5)
        self.tn.write('configure terminal\r')
        self.tn.read_until(self.promt+'(config)#', 5)
        self.tn.write('app\r')
        self.tn.read_until(self.promt+'(app)#', 5)
        self.tn.write(type+'\r')
        self.tn.read_until(self.promt+'(app)#', 5)
        print "debug cmd : "+cmd
        self.tn.write(cmd+'\r')
        s = self.tn.read_until(self.promt+'(app)#', 5)
        cut = s.split('\n')[0]
        s = s.replace(cut+'\n','')
        s = s.replace('\n'+promt+'(app)#','')
        self.tn.close()
        return s


##################### ajax call #####################

#test route
@app.route('/test')
def test():
    print "test"
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd('inner','interface view')
    print vtyret
    print 'vtyret '+vtyret+'\n'
    return "test return"

#响应登陆请求
@app.route('/ajax/data/user/checkUser')
def route_ajax_checkUser():
    retobj = {'status':1, 'message':'ok'}
    
    username = req_get('username')
    password = req_get('pw')
    if (username is None or password is None):
        retobj['message'] = 'invalid request'
        return jsonify(retobj)

    session_set('user', username)

    logininfo = {
            'lastLogin':time.strftime('%Y-%m-%d %H:%M:%S'),
            'logouttime':30,
            'userId':1,
            'username':username
            }
    retobj['status'] = 2
    retobj['login_info'] = logininfo
    return jsonify(retobj)



##################### network ########################
# 实现获取网卡信息
def impl_ajax_getNetworkList(type,filter):
    retobj = {'status':1, 'message':'ok'}
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,'interface view')
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return retobj
    vtyret = strtrim(vtyret)
    
    rows = []
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if (len(fields) != 6):
            continue
        if (filter is not None and fields[0] != filter):
            continue

        jobj = {
                'name':fields[0],
                'ip':fields[1],
                'netmask':fields[2],
                'vip':fields[3],
                'vipmask':fields[4],
                'gateway':fields[5]
                }
        rows.append(jobj)

    retobj['total'] = len(rows)
    retobj['data'] = rows
    return retobj

# 获取网卡列表	test pass
@app.route('/ajax/data/device/getNetworkList')
def route_ajax_getNetworkList():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
#debug
#    type = 'inner'
#end
    if (type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    retobj = impl_ajax_getNetworkList(type,None)
    return jsonify(retobj)

# 获取网卡信息	test pass
@app.route('/ajax/data/device/getNetworkConfig')
def route_ajax_getNetworkConfig():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    id = req_get('id')
#debug
#    type = 'inner'
#    id = 'P2'
#end
    if (id is None or type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)

    retobj = impl_ajax_getNetworkList(type,id)
    return jsonify(retobj)

# 设置网卡信息	test pass
@app.route('/ajax/data/device/setNetworkConfig')
def route_ajax_setNetworkConfig():
    retobj = {'status':1, 'message':'ok'}
    id = req_get('id')
    type = req_get('type')
    data = req_get('data')

#debug
#    id = 'test'
#    type = 'inner'
#    data = '{"Name":"P2","Ip":"12.12.12.12","NetMask":"6.6.6.6","Vip":"23.23.56.23","Vipmask":"56.231.45.12","gateway":"12.23.56.23"}'
#end

    if (data is None or id is None or type is None):
        print "debug if in"
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
    cmd = "interface edit ifname {n} ip {i} mask {m} vip {vip} vmask {vmask} gateway {g}"
    cmd = cmd.format(n=dataobj.Name,i=dataobj.Ip,m=dataobj.NetMask,vip=dataobj.Vip,vmask=dataobj.Vipmask,g=dataobj.gateway)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    print retobj
    return jsonify(retobj)



##################### IPgroup #########################
#a IP组查看		test pass
@app.route('/ajax/data/rule/getIpList')
def getIpList():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
#debug
#    type = 'inner'
#end
    if (type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    
    cmd='ipgroup view'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    id = 0
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if (len(fields) != 2):
            continue
        jobj = {
                'id' : id,
                'ipGroupName':fields[0],
                'ip':fields[1]
                }
        id = id + 1 
        jrows.append(jobj)
    retobj['page'] = len(jrows)/10 + 1
    retobj['total'] = len(jrows)
    retobj['data'] = jrows
    return jsonify(retobj)

#b IP组添加		test pass
@app.route('/ajax/data/device/addIp')
def addIp():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    ipGroupName = req_get('ipGroupName')
    ip = req_get('ip')

#debug
#    type = 'inner'
#    ipGroupName = 'group1'
#    ip = '55.55.55.55'
#end

    if ((ipGroupName is None) or (ip is None) or (type is None)):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd='ipgroup add name {n} ipset {i}'
    cmd = cmd.format(n=ipGroupName,i=ip)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

#c 获取一行IP组	test pass
@app.route('/ajax/data/device/getIpConfig')
def  getIpConfig():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    id = req_get('id')

#debug
#    type = 'inner'
#    id = '0'
#end

    if (id is None or type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd='ipgroup view'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    vtyretrow = vtyret.split('\n')[int(id)]
    grouprow = vtyretrow.split(' ')
    jrows = []
    jobj = {
            'ipGroupName':grouprow[0],
            'ip':grouprow[1]
            }
    print jobj
    jrows.append(jobj)
    retobj['data'] = jrows
    return jsonify(retobj)

#d 编辑IP组		test pass
@app.route('/ajax/data/device/setIpConfig')
def setIpConfig():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    ipGroupName = req_get('ipGroupName')
    ip = req_get('ip')

#debug
#    type = 'inner'
#    ipGroupName = 'group1'
#    ip = '55.55.55.44'
#end

    if ((ipGroupName is None) or (ip is None) or (type is None)):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd='ipgroup edit name {n} ipset {i}'
    cmd = cmd.format(n=ipGroupName,i=ip)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)
#e IP组删除		test pass
@app.route('/ajax/data/device/deleteIp')
def deleteIp():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    id = req_get('id')
#debug
#    id = '0'
#    type = 'inner'
#end
    if (id is None or type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd='ipgroup view'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    vtyretrow = vtyret.split('\n')[int(id)]
    grouprow = vtyretrow.split(' ')
    ipGroupName = grouprow[0]
    cmd = 'ipgroup del name {n}'
    cmd = cmd.format(n=ipGroupName)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)


##################### route ##########################
# 实现获取路由信息
def impl_ajax_getRouterList(type,filter):
    retobj = {'status':1, 'message':'ok'}
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,'route view')
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)

    jrows = []
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if (len(fields) != 9):
            continue
        if (filter is not None and fields[0] != filter):
            continue
        jobj = {
                'name':fields[0],
                'protocol':[fields[1]],
                'srcIp':fields[2],
                'srcPort':fields[3],
                'aimIp':fields[4],
                'aimPort':fields[5],
                'inFace':fields[6],
                'outFace':fields[7],
                'inPort':fields[8]
                }
        jrows.append(jobj)

    retobj['total'] = len(jrows)
    retobj['data'] = jrows
    return retobj

# 获取路由列表	test pass
@app.route('/ajax/data/device/getRouterList')
def route_ajax_getRouterList():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
#debug
#    type = 'inner'
#end
    if (type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    retobj = impl_ajax_getRouterList(type,None)
    return jsonify(retobj)

# 获取一个路由	test pass
@app.route('/ajax/data/device/getRouterConfig')
def getRouterConfig():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    id = req_get('id')
#debug
#    type = 'inner'
#    id = 'route1'
#end
    if (id is None or type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    retobj = impl_ajax_getRouterList(type,id)
    return jsonify(retobj)

# 添加一个路由	test pass
@app.route('/ajax/data/device/addRouter')
def route_ajax_addRouter():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    data = req_get('data')

#debug
#    type = 'inner'
#    data = '{"Name": "route1", "Protocol": "FTP", "SrcIP": "group1", "SrcPort": "5000", "AimIP": "group2", "AimPort": "5000", "OutInterface": "P3", "InnerInterface": "P2", "InnerPort": "0" }'
#end

    if (data is None or type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    
    dataobj = jstrtoobj(data)
    cmd = 'route add routename {name} proto {proto} sip {sip} sport {sport} dip {dip} dport {dport} outif {outif} inif {inif} inport {inport}'
    cmd = cmd.format(name=dataobj.Name,
                proto=dataobj.Protocol,
                sip=dataobj.SrcIP,
                sport=dataobj.SrcPort,
                dip=dataobj.AimIP,
                dport=dataobj.AimPort,
                outif=dataobj.OutInterface,
                inif=dataobj.InnerInterface,
                inport=dataobj.InnerPort)

    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

# 修改一个路由	test pass
@app.route('/ajax/data/device/setRouterConfig')
def setRouterConfig():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    data = req_get('data')
#debug
#    type = 'inner'
#    data = '{"Name": "route1", "Protocol": "FTP", "SrcIP": "group1", "SrcPort": "5000", "AimIP": "group2", "AimPort": "5000", "OutInterface": "P3", "InnerInterface": "P2", "InnerPort": "0" }'
#end
    if (data is None or type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    
    dataobj = jstrtoobj(data)
    cmd = 'route edit routename {name} proto {proto} sip {sip} sport {sport} dip {dip} dport {dport} outif {outif} inif {inif} inport {inport}'
    cmd = cmd.format(name=dataobj.Name,
                proto=dataobj.Protocol,
                sip=dataobj.SrcIP,
                sport=dataobj.SrcPort,
                dip=dataobj.AimIP,
                dport=dataobj.AimPort,
                outif=dataobj.OutInterface,
                inif=dataobj.InnerInterface,
                inport=dataobj.InnerPort)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

# 删除路由		test pass
@app.route('/ajax/data/device/deleteRouter')
def deleteRouter():
    retobj = {'status':1, 'message':'ok'}
    ut = Util_telnet(promt)
    type = req_get('type')
    sids = req_get('sids')
#debug
#    type = 'inner'
#    sids = '["route1","route2"]'
#end
    if (type is None or sids is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    sidsobj = json.loads(sids)
    for eachRoute in sidsobj:
        cmd = 'route del routename {name}'.format(name=eachRoute)
        vtyret = ut.ssl_cmd(type,cmd)
        if (vtyret is None):
            retobj['status'] = 0
            retobj['message'] = 'vty failed'
            return jsonify(retobj)
        retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)
    



##################### 规则管理 ######################
#  用户分组规则
def impl_ajax_getGroupList():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    cmd='group view'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)

    jrows = []
    id = 0
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if (len(fields) != 1):
            continue
        jobj = {
                'id' : id,
                'name':fields[0],
                }
        id = id + 1 
        jrows.append(jobj)
    retobj['page'] = len(jrows)/10 + 1
    retobj['total'] = len(jrows)
    retobj['data'] = jrows
    return retobj
#a 用户组列表	test pass
@app.route('/ajax/data/rule/getGroupList')
def getGroupList():
    retobj = impl_ajax_getGroupList()
    return jsonify(retobj)

#b 添加用户组	test pass
@app.route('/ajax/data/rule/addGroup')
def addGroup():
    retobj = {'status':1, 'message':'ok'}
    type = 'arbiter'
    data = req_get('data')
#debug
#    data = '{ "ID": "0", "Name": "g1", "HttpAccess": "1", "HttpDirection": "1", "HttpAddress": "1", "HttpIps": "1.1.1.1", "FtpAccess": "1", "FtpDirection": "1", "FtpAddress": "1", "FtpIps": "2.2.2.2", "TDCSAccess": "1", "TDCSAddress": "1", "TDCSIps": "3.3.3.3" }'
#end
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
	#1  add group
    ut = Util_telnet(promt)
    cmd='group add groupname {groupname}'
    cmd = cmd.format(groupname=dataobj.Name)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
	#2  add acl 123
    cmd='acl add index {i} proto {p} access {a} dir {d} rule_mod {m} rule_servers {ss}'
    cmd = cmd.format(i=dataobj.Name+'_1',p='HTTP',a=dataobj.HttpAccess,d=dataobj.HttpDirection,m=dataobj.HttpAddress,ss=dataobj.HttpIps)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    cmd='acl add index {i} proto {p} access {a} dir {d} rule_mod {m} rule_servers {ss}'
    cmd = cmd.format(i=dataobj.Name+'_2',p='FTP',a=dataobj.FtpAccess,d=dataobj.FtpDirection,m=dataobj.FtpAddress,ss=dataobj.FtpIps)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    cmd='acl add index {i} proto {p} access {a} dir {d} rule_mod {m} rule_servers {ss}'
    cmd = cmd.format(i=dataobj.Name+'_3',p='TDCS',a=dataobj.TDCSAccess,d='1',m=dataobj.TDCSAddress,ss=dataobj.TDCSIps)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
	#3  bind group and acl  123
    cmd='group {groupname} bind acl {index}'
    cmd = cmd.format(groupname=dataobj.Name,index=dataobj.Name+'_1')
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    cmd='group {groupname} bind acl {index}'
    cmd = cmd.format(groupname=dataobj.Name,index=dataobj.Name+'_2')
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    cmd='group {groupname} bind acl {index}'
    cmd = cmd.format(groupname=dataobj.Name,index=dataobj.Name+'_3')
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)

    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

#c 获取用户组	test torommow!!
@app.route('/ajax/data/rule/getGroupConfig')
def getGroupConfig():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    id = req_get('id')
#debug
    id = '0'
#end
    if (id is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    vtyret = impl_ajax_getGroupList()
    vtyobj = jsonify(vtyret)
    retobj['data']=[]
    jobj = {}
    name=None
    #先通过前端数据的id找到对应的用户组的 name
    for eachData in vtyobj['data']:
        if eachData['id']==int(id):
            name = eachData['name']
    if name is None:
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    #找到name之后通过group view 过滤 name_1 name_2 name_3的acl项
    ut = Util_telnet(promt)
    cmd = 'group view'
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)    
    vtyret = strtrim(vtyret)
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if fields[0]==name+'_1':
            jobj = {
                'httpAccess':fields[2],
                'httpDirection':fields[3],
                'httpAddress':fields[4],
                'httpIps':fields[5],
            }
        elif fields[0]==name+'_2':
            jobj = {
                'ftpAccess':fields[2],
                'ftpDirection':fields[3],
                'ftpAddress':fields[4],
                'ftpIps':fields[5],
            }
        elif fields[0]==name+'_3':
            jobj = {
                'tdcsAccess':fields[2],
#                'ftpDirection':fields[3],
                'tdcsAddress':fields[4],
                'tdcsIps':fields[5],
            }
    retobj['data'].append(jobj)
    return jsonify(retobj)
#d 编辑用户组	
@app.route('/ajax/data/rule/setGroupConfig')
def setGroupConfig():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    ut = Util_telnet(promt)
    data = req_get('data')
#debug
    data = '{ "ID": "0", "Name": "g1", "HttpAccess": "1", "HttpDirection": "1", "HttpAddress": "1", "HttpIps": "1.1.1.1", "FtpAccess": "1", "FtpDirection": "1", "FtpAddress": "1", "FtpIps": "2.2.2.2", "TDCSAccess": "1", "TDCSAddress": "1", "TDCSIps": "3.3.3.3" }'
#end
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
	#根据传入id获取到原组名 ,不等表示更名
    grouplist = impl_ajax_getGroupList()
    grouplistobj = jsonify(grouplist)
    oldname = grouplistobj['data'][int(dataobj.ID)]['name']
    if (dataobj.Name != oldname):
        cmd = 'group  rename groupname {old} groupname {new}'.format(old=oldname,new=dataobj.Name)
        vtyret = ut.ssl_cmd(type,cmd)
        if (vtyret is None):
            retobj['status'] = 0
            retobj['message'] = 'vty failed'
            return jsonify(retobj)
    #acl edit x3
    cmd = 'acl edit index {i} access {a} dir {d} rule_mod {m} rule_servers {ss}'
    cmd = cmd.format(i=dataobj.Name+'_1',a=dataobj.HttpAccess,d=dataobj.HttpDirection,m=dataobj.HttpAddress,ss=dataobj.HttpIps)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    cmd = 'acl edit index {i} access {a} dir {d} rule_mod {m} rule_servers {ss}'
    cmd = cmd.format(i=dataobj.Name+'_2',a=dataobj.FtpAccess,d=dataobj.FtpDirection,m=dataobj.FtpAddress,ss=dataobj.FtpIps)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    cmd = 'acl edit index {i} access {a} dir {d} rule_mod {m} rule_servers {ss}'
    cmd = cmd.format(i=dataobj.Name+'_3',a=dataobj.TDCSAccess,d=dataobj.TDCSDirection,m=dataobj.TDCSAddress,ss=dataobj.TDCSIps)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)


#e 删除用户组
@app.route('/ajax/data/rule/deleteGroup')
def deleteGroup():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    ut = Util_telnet(promt)
    id = req_get('id')
    if (id is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
	#根据传入id获取到原组名 ,不等表示更名
    grouplist = impl_ajax_getGroupList()
    grouplistobj = jsonify(grouplist)
    name = grouplistobj['data'][int(id)]['name']
    cmd='group del groupname {n}'.format(n=name)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

#2 用户规则
def impl_ajax_getUserList():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    cmd='user view'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)

    jrows = []
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if (len(fields) != 5):
            continue
        jobj = {
                'id' : id,
                'name':fields[0],
                'usergroup':fields[1],
                'ip':fields[2],
                'disable':fields[3],
                'type':fields[4]
                }
        id = id + 1 
        jrows.append(jobj)

    retobj['total'] = len(jrows)
    retobj['data'] = jrows
    return retobj
#a 用户列表查看
@app.route('/ajax/data/rule/getUserList')
def getUserList():
    retobj = impl_ajax_getUserList()
    return jsonify(retobj)
#b 用户添加
@app.route('/ajax/data/rule/addUser')
def addUser():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    data = req_get('data')
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
    ips = '{firstIP}-{lastIP}'.format(firstIP=dataobj.IP[0],lastIP=dataobj.IP[1])
    cmd='user add username {username} groupname {groupname} ip {ip} enable {e} type {t}'
    cmd = cmd.format(username=dataobj.Name,groupname=dataobj.UserGROUP,ip=ips,e=dataobj.Statue,t=dataobj.Type)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)    

#c 获取一条用户组
@app.route('/ajax/data/rule/getUserConfigGroup')
def getUserConfigGroup():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    cmd='group view'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)

    jrows = []
    id = 0
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if (len(fields) != 1):
            continue
        jobj = {
                'id' : id,
                'group':fields[0],
                }
        id = id + 1 
        jrows.append(jobj)
    retobj['total'] = len(jrows)
    retobj['data'] = jrows
    return jsonify(retobj)
#d 获取一条用户
@app.route('/ajax/data/rule/getUserConfig')
def getUserConfig():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    id = req_get('id')
    if (id is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    vtyret = impl_ajax_getUserList()
    vtyobj = jsonify(vtyret)
    retobj['data'] = []
    for eachdata in vtyobj['data']:
        if (eachdata['id'] == int(id)):
            retobj['data'].append(eachdata)
    return jsonify(retobj)
#e 编辑一条用户
@app.route('/ajax/data/rule/setUserConfig')
def setUserConfig():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    data = req_get('data')
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
    ips = '{firstIP}-{lastIP}'.format(firstIP=dataobj.IP[0],lastIP=dataobj.IP[1])
    cmd='user edit username {username} groupname {groupname} ip {ip} enable {e} type {t}'
    cmd = cmd.format(username=dataobj.Name,groupname=dataobj.UserGroup,ip=ips,e=dataobj.Statue,t=dataobj.Type)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

#f 删除一条用户
@app.route('/ajax/data/rule/deleteUser')
def deleteUser():
    retobj = {'status':1, 'message':'ok'}
    ut = Util_telnet(promt)
    type='inner'
    sids = req_get('sids')
    if (sids is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    sidsobj = json.loads(sids)
    vtyret = impl_ajax_getUserList()
    vtyobj = jsonify(vtyret)
    for eachid in sidsobj:
        for eachdata in vtyobj['data']:
            if (eachdata['id'] == int(eachid)):
                cmd='ipmac del username {username}'.format(username=eachdata['name'])
                vtyret = ut.ssl_cmd(type,cmd)
                if (vtyret is None):
                    retobj['status'] = 0
                    retobj['message'] = 'vty failed'
                    return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)



#3 IP-MAC规则
def impl_ajax_getIpMacList():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    cmd='ipmac view'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)

    jrows = []
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if (len(fields) != 5):
            continue 
        jobj = {
                'id' : id,
                'name':fields[0],
                'ip':fields[1],
                'mac':fields[2],
                'behave':fields[3],
                'state':fields[4]
                }
        id = id + 1
        jrows.append(jobj)

    retobj['total'] = len(jrows)
    retobj['data'] = jrows
    return retobj
#a IP-MAC列表查看
@app.route('/ajax/data/rule/getIpMacList')
def getIpMacList():
    retobj = impl_ajax_getIpMacList()
    return jsonify(retobj)
#b IP-MAC添加
@app.route('/ajax/data/rule/addIpMac')
def addIpMac():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    data = req_get('data')
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)	
    dataobj = jstrtoobj(data)
    cmd='ipmac add device {name} ip {ip} mac {mac} action {a} enable {e}'
    cmd = cmd.format(name=dataobj.Name,ip=dataobj.IP,mac=dataobj.MAC,a=dataobj.Behave,e=dataobj.State)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)    
#c 获取一条IP-MAC
@app.route('/ajax/data/rule/getIpMacConfig')
def getIpMacConfig():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    id = req_get('id')
    if (id is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    vtyret = impl_ajax_getIpMacList()
    vtyobj = jsonify(vtyret)
    retobj['data'] = []
    for eachdata in vtyobj['data']:
        if (eachdata['id'] == int(id)):
            retobj['data'].append(eachdata)
    return jsonify(retobj)
#d 编辑一条IP-MAC
@app.route('/ajax/data/rule/setIpMacConfig')
def setIpMacConfig():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    data = req_get('data')
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)	
    dataobj = jstrtoobj(data)
    cmd='ipmac edit device {name} ip {ip} mac {mac} action {a} enable {e}'
    cmd = cmd.format(name=dataobj.Name,ip=dataobj.IP,mac=dataobj.MAC,a=dataobj.Behave,e=dataobj.State)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

#e 删除一条IP-MAC
@app.route('/ajax/data/rule/deleteIpMac')
def deleteIpMac():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    id = req_get('id')
    if (id is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    vtyret = impl_ajax_getIpMacList()
    vtyobj = jsonify(vtyret)
    for eachdata in vtyobj['data']:
        if (eachdata['id'] == int(id)):
            cmd='ipmac del ip {ip}'.format(ip=eachdata['ip'])
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)



##################### templates ######################
# 响应页面请求
@app.route('/')
def route_root():
    return redirect('index.html')
@app.route('/<path>')
@app.route('/templates/<path>')
@app.route('/templates/device/<path>')
@app.route('/templates/device/admin/<path>')
@app.route('/templates/device/arbiter/<path>')
@app.route('/templates/device/inner/<path>')
@app.route('/templates/device/inner/dialog/<path>')
@app.route('/templates/device/outer/<path>')
@app.route('/templates/device/outer/dialog/<path>')
@app.route('/templates/device/router/<path>')
@app.route('/templates/device/router/dialog/<path>')
@app.route('/templates/event/<path>')
@app.route('/templates/home/<path>')
@app.route('/templates/log/<path>')
@app.route('/templates/log/audit/<path>')
@app.route('/templates/log/login/<path>')
@app.route('/templates/log/sys/<path>')
@app.route('/templates/rule/<path>')
@app.route('/templates/session/<path>')
@app.route('/templates/state/<path>')
@app.route('/templates/utility/<path>')
def route_templates(path):
    if (path == 'favicon.ico'):
        return ''

    uname = session_get('user')
    if (uname is None and path != 'login.html'):
        return redirect('login.html')

    if (request.path[0:11] == '/templates/'):
        path = request.path[10:]
    return render_template(path)


################## main ####################

# main
if __name__ == '__main__':
    app.secret_key = 'python flask gap20'
    app.run(host='0.0.0.0', port=8888, debug=False)

