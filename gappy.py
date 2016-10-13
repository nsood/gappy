#coding=utf-8  
from flask import Flask, request, render_template, make_response, session, redirect, jsonify
import json
import sqlite3
import time
from flask_cors import CORS
import os, ConfigParser
import re
import telnetlib
import ssl
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


#------------------------begin-----------op class-------------------------------------
class OpObj(object):
    def __init__(self):
        self.op = ['add', 'del', 'edit', 'view']
        self.mach = ['inner', 'arbiter', 'outer']

    def write_op_log(self, ip, user, op, mach, content):
        cmd='sqlite3 /data/gap_sqlite3_db.log "insert into op_table(ip,user,op,type, content) values(\'{0}\', \'{1}\',\'{2}\',\'{3}\',\'{4}\')"'
        cmd = cmd.format(ip, user, op, mach, content)
        os.system(cmd)
#------------------------end-----------op class-------------------------------------

#------------------------begin-----------login class-------------------------------------
class LoginObj(object):
    def __init__(self):
        self.state = ['ok', 'failed']

    def write_login_log(self, ip, user, state, content):
        cmd='sqlite3 /data/gap_sqlite3_db.log "insert into login_table(ip,user,state, content) values(\'{0}\', \'{1}\',\'{2}\',\'{3}\')"'
        cmd = cmd.format(ip, user, state, content)
        os.system(cmd)
#------------------------end-----------login class-------------------------------------

# 数据库借口
def get_sql_data(db_name,cmd):
    line = 'sqlite3 {db} "{c}"'.format(db=db_name,c=cmd)
    print "debug sql cmdline "+line
    return os.popen(line).read()

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
        print "debug util ret:"+s
        cut = s.split('\n')[0]
        s = s.replace(cut+'\n','')
        s = s.replace(promt+'(app)#','')
        self.tn.close()
        return s

def get_total_num(s):
    print "debug s: "+s
    ss = s.split(',')
    if len(ss)!=3:
        return 0
    ss = ss[2]
    if ss==']':
        return 0
    ss = ss.replace('totalline=','')
    ss = ss.split('\n')[0]
    ss = ss.split(']')[0]
    try:
        ints = int(ss)
        return ints
    except:
        return 0
##################### ajax call #####################

#test route
@app.route('/test')
def test():
    print "test"
    test = req_get('test')
    if test is None:
        return "return None"
    return test
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd('inner','interface view')
    print vtyret
    print 'vtyret '+vtyret+'\n'
    return "test return"


##################### 1.2网络配置 ########################
# 实现获取网卡信息
def impl_ajax_getNetworkList(type,filter):
    retobj = {'status':1, 'message':'ok'}
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,'interface view')
    if (vtyret is None or vtyret.find('%')==0):
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
    name = req_get('name')
#debug
#    type = 'inner'
#    name = 'P2'
#end
    if (name is None or type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)

    retobj = impl_ajax_getNetworkList(type,name)
    return jsonify(retobj)

# 设置网卡信息	test pass
@app.route('/ajax/data/device/setNetworkConfig')
def route_ajax_setNetworkConfig():
    retobj = {'status':1, 'message':'ok'}
    name = req_get('name')
    type = req_get('type')
    data = req_get('data')
    operate = req_get('operate')

#debug
#    name = 'test'
#    type = 'inner'
#    data = '{"Name":"P2","Ip":"12.12.12.12","NetMask":"6.6.6.6","Vip":"23.23.56.23","Vipmask":"56.231.45.12","gateway":"12.23.56.23"}'
#end

    if (data is None or name is None or type is None or operate is None):
        print "debug if in"
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
    cmd = "interface {opt} ifname {n} ip {i} mask {m} vip {vip} vmask {vmask} gateway {g}"
    cmd = cmd.format(opt=operate,n=dataobj.Name,i=dataobj.Ip,m=dataobj.NetMask,vip=dataobj.Vip,vmask=dataobj.Vipmask,g=dataobj.gateway)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    print retobj
    return jsonify(retobj)


##################### 1.3双机热备 #########################
# a 获取热备数据
@app.route('/ajax/data/device/getDoubleConfig')
def getDoubleConfig():
    retobj = {
        'status':1, 
        'message':'ok',
        'data': [
            {
            "haInner": "",
            "haPortInner": "",
            "haOuter": "",
            "haRole": "",
            "prior": "",
            "haBackupInner": "",
            "haBackupOuter": "",
            "haPriorBackup": ""
            }
        ]
    }
    cmd = "vtysh -c 'configure terminal' -c 'ha' -c 'show state'"
    ret = os.popen(cmd).read()
    if ret=='':
        retobj['status'] = 0
        retobj['message'] = 'not get ha information'
        return jsonify(retobj)
    ret = strtrim(ret)
    state = ret.split('\n')
    rows = len(state)
    if rows<6:
        retobj['status'] = 0
        retobj['message'] = 'ha disabled'
        return jsonify(retobj)
    haInner=''
    haPortInner=''
    haOuter=''
    haRole=''
    prior=''
    haBackupInner=''
    haBackupOuter=''
    haPriorBackup=''

    for line in state:
        if line.find('init priority')>=0:
            prior = line.split(' : ')[1]
        elif line.find('running state')>=0:
            haRole = line.split(' : ')[1]=='STB' and 1 or 0
        elif line.find('local ip')>=0:
            haInner = line.split(' : ')[1]
        elif line.find('local port')>=0:
            haPortInner = line.split(' : ')[1]
        elif line.find('OAU')>=0:
            line_c = line.split(' ')
            haOuter = line_c[1]
        elif line.find('OSU')>=0:
            line_c = line.split(' ')
            haBackupOuter = line_c[1]
            haPriorBackup = int(line_c[3])
        elif line.find('OA ')>=0:
            line_c = line.split(' ')
            haBackupInner = line_c[1]
        else :
            continue
    jrows=[]
    data = {
        "haInner": haInner,
        "haPortInner": haPortInner,
        "haOuter": haOuter,
        "haRole": haRole,
        "prior": prior,
        "haBackupInner": haBackupInner,
        "haBackupOuter": haBackupOuter,
        "haPriorBackup": haPriorBackup
    }
    jrows.append(data)
    retobj['data']=jrows
    return jsonify(retobj)

# b 设置热备参数
@app.route('/ajax/data/device/setDoubleConfig')
def setDoubleConfig():
    retobj = {'status':1, 'message':'ok'}
    data = req_get('data')
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'input error'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
    



##################### 1.4登录配置 #########################
#a 获取登录配置
@app.route('/ajax/data/device/getLoginConfig')
def getLoginConfig():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    if (type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)

    sqlret = get_sql_data('/etc/gap_sqlite3_db.conf','select * from user_conf_table where id=1')
    if sqlret=='':
        retobj['status'] = 0
        retobj['message'] = 'sql error'
        return jsonify(retobj)
    sqlret = strtrim(sqlret)
    sqlret = sqlret.split('\n')
    fields = sqlret[0].split('|')
    data=[]
    if type=='inner':
        jobj={
            'serial':fields[3],
            'ssh':fields[2]
        }
    else:
        jobj={
            'serial':fields[5],
            'ssh':fields[4]
        }
    data.append(jobj)
    retobj['data']=data
    return jsonify(retobj)
#b 设置登录配置
@app.route('/ajax/data/device/setLoginConfig')
def setLoginConfig():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    data = req_get('data')
    if (type is None or data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
    if type=='inner':
        cmd = "update user_conf_table set inner_ssh={i_s},inner_console={i_c} where id=1"
    else:
        cmd = "update user_conf_table set outer_ssh={i_s},outer_console={i_c} where id=1"
    cmd = cmd.format(i_s=dataobj.ssh,i_c=dataobj.serial)

    sqlret = get_sql_data('/etc/gap_sqlite3_db.conf',cmd)
    if sqlret!='':
        retobj['status'] = 0
        retobj['message'] = 'sql error'
        return jsonify(retobj)
    return jsonify(retobj)


##################### 1.5 通用设置 #####################
##################### 1.5.1系统时间 #####################
#a 获取时间设置
@app.route('/ajax/data/device/getSysTimeConfig')
def getSysTimeConfig():
    retobj = {'status':1, 'message':'ok'}
    type = 'inner'
    cmd='show status'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type, cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['message'] = 'vty error'
        retobj['status'] = 0
        return jsonify(retobj)
    data = []
    vtyret = strtrim(vtyret)
    for line in vtyret.split('\n'):
        fields = line.split('=')
        if (fields[0] == 'Time'):
            jobj = {
                'systime':fields[1]
            }
            data.append(jobj)
    retobj['data'] = data
    return jsonify(retobj)
#b 编辑时间设置 保存数据
@app.route('/ajax/data/device/setSysTimeConfig')
def setSysTimeConfig():
    retobj = {'status':1, 'message':'ok'}
    type = 'inner'
    data = req_get('data')
    dataobj = jstrtoobj(data)

    ut = Util_telnet(promt)

    if (dataobj.status=='1' and dataobj.serverAddress is not None):
        cmd = 'set ntp {ip}'.format(ip=dataobj.serverAddress)
        vtyret = ut.ssl_cmd(type, cmd)
        if (vtyret is None or vtyret.find('%')==0):
            retobj['message'] = 'set ntp error'
            retobj['status'] = 0
            return jsonify(retobj)
    elif (dataobj.status=='0' and dataobj.sysTime is not None):
        Time = dataobj.sysTime.replace('-','/')
        Time = Time.replace(' ','-')
        cmd = 'set time {time}'.format(time=Time)
        vtyret = ut.ssl_cmd(type, cmd)
        if (vtyret is None or vtyret.find('%')==0):
            retobj['message'] = 'set time error'
            retobj['status'] = 0
            return jsonify(retobj)
    else :
        retobj['message'] = 'input error'
        retobj['status'] = 0
        return jsonify(retobj)
    return jsonify(retobj)
##################### 1.5.2证书更新 #####################
##################### 1.5.3系统升级 #####################
##################### 1.5.4系统重置 #####################
#a 恢复出厂设置
#b 重启
#c 关闭


##################### 1.6IP组配置 #########################
#a IP组查看		test pass
@app.route('/ajax/data/device/getIpList')
def getIpList():
    retobj = {'status':1, 'message':'ok'}
    page = req_get('page')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)

    type = 'outer'
    cmd='ipgroup view pgindex {p} pgsize 10'.format(p=page)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    id = 0
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 2):
            continue
        jobj = {
                'id' : id,
                'ipGroupName':fields[0],
                'ip':fields[1]
                }
        id = id + 1 
        jrows.append(jobj)
    retobj['page'] = page
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

#b IP组添加		test pass
@app.route('/ajax/data/device/addIp')
def addIp():
    retobj = {'status':1, 'message':'ok'}
#    type = req_get('type')
    data = req_get('data')

#debug
#    type = 'inner'
#    ipGroupName = 'group1'
#    ip = '55.55.55.55'
#end

    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
    cmd='ipgroup add name {n} ipset {i}'
    cmd = cmd.format(n=dataobj.Name,i=dataobj.Ips)
    ut = Util_telnet(promt)

    type = 'outer'
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)

    type = 'inner'
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

#c 获取一行IP组	test pass
@app.route('/ajax/data/device/getIpConfig')
def  getIpConfig():
    retobj = {'status':1, 'message':'ok'}
#    type = req_get('type')
    name = req_get('name')

#debug
#    name = '0'
#end
    if (name is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd='ipgroup view pgindex 0 pgsize 10'
    type = 'outer'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if (len(fields) != 2 or fields[0]!=name):
            continue
        jrows = []
        jobj = {
            'ipGroupName':fields[0],
            'ip':fields[1]
            }
        jrows.append(jobj)
        break
    retobj['data'] = jrows
    return jsonify(retobj)

#d 编辑IP组		test pass
@app.route('/ajax/data/device/setIpConfig')
def setIpConfig():
    retobj = {'status':1, 'message':'ok'}
    data = req_get('data')

    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
    cmd='ipgroup edit name {n} ipset {i}'
    cmd = cmd.format(n=dataobj.Name,i=dataobj.Ips)
    ut = Util_telnet(promt)

    type = 'outer'
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)

    type = 'inner'
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)
#e IP组删除		test pass
@app.route('/ajax/data/device/deleteIp')
def deleteIp():
    retobj = {'status':1, 'message':'ok'}
    name = req_get('name')
    print name

    if (name is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)

    cmd = 'ipgroup del name {n}'
    cmd = cmd.format(n=name)
    print cmd
    type = 'outer'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)

    type = 'inner'
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)


##################### 1.7路由配置 ##########################
# 实现获取路由信息
def impl_ajax_getRouterList(type,page,filter):
    retobj = {'status':1, 'message':'ok'}
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,'route view pgindex {p} pgsize 10'.format(p=page))
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)

    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
            print "debug:"+totalline
        if (len(fields) != 9):
            continue
        if (filter is not None and fields[0] != filter):
            continue
        jobj = {
                'name':fields[0],
                'protocol':fields[1],
                'srcIp':fields[2],
                'srcPort':fields[3],
                'aimIp':fields[4],
                'aimPort':fields[5],
                'inFace':fields[6],
                'outFace':fields[7],
                'inPort':fields[8]
                }
        jrows.append(jobj)

    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return retobj

#a 获取路由列表	test pass
@app.route('/ajax/data/device/getRouterList')
def route_ajax_getRouterList():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    page = req_get('page')
#debug
#    type = 'inner'
#end
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    retobj = impl_ajax_getRouterList(type,page,None)
    return jsonify(retobj)

#b 添加一个路由	test pass
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
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

#c 获取IP组		test pass
@app.route('/ajax/data/device/getRouterConfigGroup')
def getRouterConfigGroup():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
#debug
#    type = 'inner'
#end
    if (type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    
    cmd='ipgroup view pgindex 0 pgsize 10'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
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
                'group':fields[0],
                }
        id = id + 1 
        jrows.append(jobj)
    retobj['data'] = jrows
    return jsonify(retobj)

#d 获取一个路由	test pass
@app.route('/ajax/data/device/getRouterConfig')
def getRouterConfig():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    name = req_get('name')
#debug
#    type = 'inner'
#    name = 'route1'
#end
    if (name is None or type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    retobj = impl_ajax_getRouterList(type,0,name)
    return jsonify(retobj)

#e 修改一个路由	test pass
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
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

#f 删除路由		test pass
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
    sids = sids.split(',')
    for eachRoute in sids:
        cmd = 'route del routename {name}'.format(name=eachRoute)
        vtyret = ut.ssl_cmd(type,cmd)
        if (vtyret is None or vtyret.find('%')==0):
            retobj['status'] = 0
            retobj['message'] = 'vty failed'
            return jsonify(retobj)
        retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)
    

##################### 1.8管理员配置 ##########################
# a 管理员列表
@app.route('/ajax/data/device/getAdminList')
def getAdminList():
    retobj = {'status':1, 'message':'ok'}
    page = req_get('page')
    role = req_get('role')
    if (page is None or role is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = "select * from admin_table where role={r}".format(r=int(role))
    sqlret = get_sql_data('/etc/gap_sqlite3_db.conf',cmd)
    sqlret = strtrim(sqlret)
    sqlret = sqlret.split('\n')
    rows = len(sqlret)
    if (int(page)-1)*10>rows:
        retobj['status'] = 0
        retobj['message'] = 'page num error'
        return jsonify(retobj)

    endrow = int(page)*10
    if rows<=endrow:
        endrow=rows
    sqlres = sqlret[(int(page)*10-10):endrow]
    id=0
    jrows = []
    for eachItem in sqlret:
        item = eachItem.split('|')
        jobj = {
            'name':item[1],
            'role':item[3],
            'datelogout':item[4],
            'id':id
        }
        id = id + 1
        jrows.append(jobj)
    retobj['total'] = rows
    retobj['data'] = jrows
    return jsonify(retobj)

# b 添加管理员
@app.route('/ajax/data/device/addAdmin')
def addAdmin():
    retobj = {'status':1, 'message':'ok'}
    data = req_get('data')
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
    cmd = "insert into amdin_table(id,user,passwd,role,datelogin,loginerrtimes) vaiues(NULL,'{u}','{p}',{r},'{d}',0)"
    cmd = cmd.format(u=dataobj.name,p=dataobj.password,r=dataobj.role,d='')

    sqlret = get_sql_data('/etc/gap_sqlite3_db.conf',cmd)
    if sqlret!='':
        retobj['status'] = 0
        retobj['message'] = 'insert sql error'
        return jsonify(retobj)
    return jsonify(retobj)

# c 编辑管理员
@app.route('/ajax/data/device/setAdminConfig')
def setAdminConfig():
    retobj = {'status':1, 'message':'ok'}
    data = req_get('data')
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
    cmd = "update admin_table set passwd='{p}' where user='{u}'"
    cmd = cmd.format(u=dataobj.name,p=dataobj.password)
    sqlret = get_sql_data('/etc/gap_sqlite3_db.conf',cmd)
    if sqlret!='':
        retobj['status'] = 0
        retobj['message'] = 'update sql error'
        return jsonify(retobj)
    return jsonify(retobj)

# d 删除管理员
@app.route('/ajax/data/device/deleteAdmin')
def deleteAdmin():
    retobj = {'status':1, 'message':'ok'}
    name = req_get('name')
    if (name is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = "delete from admin_table where user='{u}'"
    cmd = cmd.format(u=name)

    sqlret = get_sql_data('/etc/gap_sqlite3_db.conf',cmd)
    if sqlret!='':
        retobj['status'] = 0
        retobj['message'] = 'delete sql error'
        return jsonify(retobj)
    return jsonify(retobj)

# e 检查管理员存在
@app.route('/ajax/data/device/checkAdminName')
def checkAdminName():
    retobj = {'status':1, 'message':'ok'}
    name = req_get('name')
    if (name is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = "select * from admin_table where user='{u}'"
    cmd = cmd.format(u=name)
    sqlret = get_sql_data('/etc/gap_sqlite3_db.conf',cmd)
    sqlret = strtrim(sqlret)
    sqlret = sqlret.split('\n')
    rows = len(sqlret)
    if len(sqlret)!=1 or sqlret[1]=='':
        retobj['status'] = 0
        retobj['message'] = 'check admin sql error'
        return jsonify(retobj)
    return jsonify(retobj)

# f 管理员登录配置
@app.route('/ajax/data/device/saveAdminConfig')
def saveAdminConfig():
    retobj = {'status':1, 'message':'ok'}
    time = req_get('time')
    num = req_get('num')
    if (time is None or num is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)

    cmd1 = "select * from user_conf_table"
    cmd2 = "insert into user_conf_table(id,timelogout,timestrylogin) values(1,{t},{n})"
    cmd3 = "update user_conf_table set timelogout={t},timestrylogin={n} where id=1"
    cmd2 = cmd2.format(t=int(time),n=int(num))
    cmd3 = cmd3.format(t=int(time),n=int(num))

    sqlret = get_sql_data('/etc/gap_sqlite3_db.conf',cmd1)
    if sqlret=='':
        sqlret = get_sql_data('/etc/gap_sqlite3_db.conf',cmd2)
    else:
        sqlret = get_sql_data('/etc/gap_sqlite3_db.conf',cmd3)
    sqlret = strtrim(sqlret)
    sqlret = sqlret.split('\n')
    if sqlret!='':
        retobj['status'] = 0
        retobj['message'] = 'insert sql error'
        return jsonify(retobj)
    return jsonify(retobj)



##################### 2 规则管理 ######################
##################### 2.1 用户分组规则#################
def impl_ajax_getGroupList(page):
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    cmd='group view pgindex {p} pgsize 10'.format(p=page)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    totalline = '[,,]'
    jrows = []
    id = 0
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 1) or len(fields[0])>30:
            continue
        jobj = {
                'id' : id,
                'name':fields[0],
                }
        id = id + 1 
        jrows.append(jobj)
    retobj['page'] = len(jrows)/10 + 1
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return retobj
#a 用户组列表	test pass
@app.route('/ajax/data/rule/getGroupList')
def getGroupList():
    retobj = {'status':1, 'message':'ok'}
    page = req_get('page')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    retobj = impl_ajax_getGroupList(page)
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

    if dataobj.HttpIps=='':
        HttpIps = '0.0.0.0'
    else:
        HttpIps = dataobj.HttpIps
    if dataobj.FtpIps=='':
        FtpIps = '0.0.0.0'
    else:
        FtpIps = dataobj.FtpIps
    if dataobj.TDCSIps=='':
        TDCSIps = '0.0.0.0'
    else:
        TDCSIps = dataobj.TDCSIps
	#1  add group
    ut = Util_telnet(promt)
    cmd='group add groupname {groupname}'
    cmd = cmd.format(groupname=dataobj.Name)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
	#2  add acl 123
    cmd='acl add index {i} proto {p} access {a} dir {d} rule_mod {m} rule_servers {ss}'
    cmd = cmd.format(i=dataobj.Name+'_HTTP',p='HTTP',a=dataobj.HttpAccess,d=dataobj.HttpDirection,m=dataobj.HttpAddress,ss=HttpIps)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    cmd='acl add index {i} proto {p} access {a} dir {d} rule_mod {m} rule_servers {ss}'
    cmd = cmd.format(i=dataobj.Name+'_FTP',p='FTP',a=dataobj.FtpAccess,d=dataobj.FtpDirection,m=dataobj.FtpAddress,ss=FtpIps)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    cmd='acl add index {i} proto {p} access {a} dir {d} rule_mod {m} rule_servers {ss}'
    cmd = cmd.format(i=dataobj.Name+'_TDCS',p='TDCS',a=dataobj.TDCSAccess,d='1',m=dataobj.TDCSAddress,ss=TDCSIps)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
	#3  bind group and acl  123
    cmd='group {groupname} bind acl {index}'
    cmd = cmd.format(groupname=dataobj.Name,index=dataobj.Name+'_HTTP')
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    cmd='group {groupname} bind acl {index}'
    cmd = cmd.format(groupname=dataobj.Name,index=dataobj.Name+'_FTP')
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    cmd='group {groupname} bind acl {index}'
    cmd = cmd.format(groupname=dataobj.Name,index=dataobj.Name+'_TDCS')
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)

    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

#c 获取用户组	test pass
@app.route('/ajax/data/rule/getGroupConfig')
def getGroupConfig():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    name = req_get('name')

    if (name is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)

    jrows=[]
    ut = Util_telnet(promt)
    cmd = 'group view pgindex 0 pgsize 10'
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)    
    vtyret = strtrim(vtyret)
    print vtyret
    httpAccess=None
    httpDirection=None
    httpAddress=None
    httpIps=None
    ftpAccess=None
    ftpDirection=None
    ftpAddress=None
    ftpIps=None
    tdcsAccess=None
    tdcsAddress=None
    tdcsIps=None
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if fields[0]==name+'_TDCS':
                tdcsAccess=fields[2]
                tdcsAddress=fields[4]
                tdcsIps=fields[5]
        elif fields[0]==name+'_FTP':
                ftpAccess=fields[2]
                ftpDirection=fields[3]
                ftpAddress=fields[4]
                ftpIps=fields[5]
        elif fields[0]==name+'_HTTP':
                httpAccess=fields[2]
                httpDirection=fields[3]
                httpAddress=fields[4]
                httpIps=fields[5]
    jobj = {
        'id':'0',
        'name':name,
        'httpAccess':httpAccess,
        'httpDirection':httpDirection,
        'httpAddress':httpAddress,
        'httpIps':httpIps,
        'ftpAccess':ftpAccess,
        'ftpDirection':ftpDirection,
        'ftpAddress':ftpAddress,
        'ftpIps':ftpIps,
        'tdcsAccess':tdcsAccess,
        'tdcsAddress':tdcsAddress,
        'tdcsIps':tdcsIps
    }
    jrows.append(jobj)
    print jobj
    print jrows
    retobj['data'] = jrows
    return jsonify(retobj)
#d 编辑用户组	test pass
@app.route('/ajax/data/rule/setGroupConfig')
def setGroupConfig():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    ut = Util_telnet(promt)
    data = req_get('data')
#debug
#    data = '{ "Name": "g3", "HttpAccess": "1", "HttpDirection": "1", "HttpAddress": "1", "HttpIps": "1.1.1.1", "FtpAccess": "1", "FtpDirection": "1", "FtpAddress": "1", "FtpIps": "2.2.2.2", "TDCSAccess": "1", "TDCSAddress": "1", "TDCSIps": "3.3.3.3" }'
#end
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)

    oldname = dataobj.oldName
    if (dataobj.Name != oldname):
        cmd = 'group  rename groupname {old} newname {new}'.format(old=oldname,new=dataobj.Name)
        vtyret = ut.ssl_cmd(type,cmd)
        if (vtyret is None or vtyret.find('%')==0):
            retobj['status'] = 0
            retobj['message'] = 'vty failed'
            return jsonify(retobj)
    #acl edit x3
    cmd = 'acl edit index {i} access {a} dir {d} rule_mod {m} rule_servers {ss}'
    cmd = cmd.format(i=dataobj.Name+'_HTTP',a=dataobj.HttpAccess,d=dataobj.HttpDirection,m=dataobj.HttpAddress,ss=dataobj.HttpIps)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    cmd = 'acl edit index {i} access {a} dir {d} rule_mod {m} rule_servers {ss}'
    cmd = cmd.format(i=dataobj.Name+'_FTP',a=dataobj.FtpAccess,d=dataobj.FtpDirection,m=dataobj.FtpAddress,ss=dataobj.FtpIps)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    cmd = 'acl edit index {i} access {a} dir {d} rule_mod {m} rule_servers {ss}'
    cmd = cmd.format(i=dataobj.Name+'_TDCS',a=dataobj.TDCSAccess,d='3',m=dataobj.TDCSAddress,ss=dataobj.TDCSIps)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

#e 删除用户组	test pass
@app.route('/ajax/data/rule/deleteGroup')
def deleteGroup():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    ut = Util_telnet(promt)
    name = req_get('name')

    if (name is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)

    cmd='group del groupname {n}'.format(n=name)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

##################### 2.2 用户规则#####################
def impl_ajax_getUserList(page):
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    cmd='user view pgindex {p} pgsize 10'.format(p=page)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
#    print "debug : "+ vtyret
    jrows = []
    id=0
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 6):
            continue
        if fields[4]=='1':
            fields[4]='encrypt'
        else:
            fields[4]='nonencrypt'
        ips = fields[2].split('-')
        if len(ips)==1:
            ips = fields[2]
        elif len(ips)==2:
            ips = '{ip1},{ip2}'.format(ip1=ips[0],ip2=ips[1])
        else:
            retobj['status'] = 0
            retobj['message'] = 'ips error'
            return jsonify(retobj)
        jobj = {
                'id' : id,
                'name':fields[0],
                'usergroup':fields[1],
                'ip':ips,
                'mac':fields[3],
                'disable':fields[4],
                'type':fields[5]
                }
        id = id + 1 
        jrows.append(jobj)

    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return retobj
#a 用户列表查看	test pass
@app.route('/ajax/data/rule/getUserList')
def getUserList():
    retobj = {'status':1, 'message':'ok'}
    page = req_get('page')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    retobj = impl_ajax_getUserList(page)
#    print retobj
    return jsonify(retobj)
#b 用户添加		test pass
@app.route('/ajax/data/rule/addUser')
def addUser():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    data = req_get('data')
#debug
#    data = '{"Type": "1", "Name": "u5","UserGroup": "g2", "IP": "2.2.2.2,2.2.2.5","MAC": "11:22:33:44:55:66", "Statue": "1" }'
#end
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
    ipstr = dataobj.IP.split(',')
    if len(ipstr)==2:
        ips = '{firstIP}-{lastIP}'.format(firstIP=ipstr[0],lastIP=ipstr[1])
    elif len(ipstr)==1:
        ips = ipstr[0]
    if dataobj.Type=='encrypt':
        Type = '1'
    else:
        Type = '0'
#    print ips
    cmd='user add username {username} groupname {groupname} ip {ip} mac {m} enable {e} type {t}'
    cmd = cmd.format(username=dataobj.Name,groupname=dataobj.UserGroup,ip=ips,m=dataobj.MAC,e=dataobj.Statue,t=Type)
#    print "debug : " + cmd
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
#    print "debug : " + vtyret
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)    

#c 获取用户组	test pass
@app.route('/ajax/data/rule/getUserConfigGroup')
def getUserConfigGroup():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    cmd='group view pgindex 0 pgsize 10'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)

    jrows = []
    id = 0
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 1) or len(fields[0])>30:
            continue
        jobj = {
                'id' : id,
                'group':fields[0]
                }
        id = id + 1 
        jrows.append(jobj)
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)
#d 获取用户		test pass
@app.route('/ajax/data/rule/getUserConfig')
def getUserConfig():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    name = req_get('name')

    if (name is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    vtydirc = impl_ajax_getUserList(0)
    retobj['data'] = []

    for eachdata in vtydirc['data']:
        if (eachdata['name'] == name):
            if eachdata['type']=='1':
                eachdata['type']='encrypt'
            else:
                eachdata['type']='nonencrypt'
            retobj['data'].append(eachdata)
    return jsonify(retobj)
#e 编辑用户		test pass
@app.route('/ajax/data/rule/setUserConfig')
def setUserConfig():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    data = req_get('data')
#debug
#    data = '{ "Type": "encrypt", "Name": "u3","UserGroup": "g2", "IP": "[2.2.2.2,2.2.2.5]", "MAC": "11:22:33:44:55:66","Statue": "1" }'
#end
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
    ipstr = dataobj.IP.split(',')
    if len(ipstr)==2:
        ips = '{firstIP}-{lastIP}'.format(firstIP=ipstr[0],lastIP=ipstr[1])
    elif len(ipstr)==1:
        ips = ipstr[0]

    if dataobj.Type=='encrypt':
        Type = '1'
    else:
        Type = '0'
    cmd='user edit username {username} groupname {groupname} ip {ip} mac {m} enable {e} type {t}'
    cmd = cmd.format(username=dataobj.Name,groupname=dataobj.UserGroup,ip=ips,m=dataobj.MAC,e=dataobj.Statue,t=Type)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

#f 删除用户		test pass
@app.route('/ajax/data/rule/deleteUser')
def deleteUser():
    retobj = {'status':1, 'message':'ok'}
    ut = Util_telnet(promt)
    type='arbiter'
    sids = req_get('sids')

    if (sids is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    sids = sids.split(',')
    vtydirc = impl_ajax_getUserList(0)
    for eachname in sids:
        for eachdata in vtydirc['data']:
            if (eachdata['name'] == eachname):
                cmd='user del username {username}'.format(username=eachdata['name'])
                vtyret = ut.ssl_cmd(type,cmd)
                if (vtyret is None or vtyret.find('%')==0):
                    retobj['status'] = 0
                    retobj['message'] = 'vty failed'
                    return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)


###################### 2.3 IP-MAC规则###################
def impl_ajax_getIpMacList(page):
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    cmd='ipmac view pgindex {p} pgsize 10'.format(p=page)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
#    print "debug 1 :"+vtyret
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
#    print "debug 2 :"+vtyret
    jrows = []
    id=0
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
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

    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return retobj
#a IP-MAC列表	test pass
@app.route('/ajax/data/rule/getIpMacList')
def getIpMacList():
    retobj = {'status':1, 'message':'ok'}
    page=req_get('page')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    retobj = impl_ajax_getIpMacList(page)
    return jsonify(retobj)
#b IP-MAC添加	test pass
@app.route('/ajax/data/rule/addIpMac')
def addIpMac():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    data = req_get('data')
#debug
#    data = '{ "Name": "d11", "IP": "3.3.3.3", "MAC": "03:66:FE:57:B4:90", "State": "1","Behave":"0" }'
#end
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    dataobj = jstrtoobj(data)
    if dataobj.Behave=='0':
        behave = 'b'
    else:
        behave = 'w'
    cmd='ipmac add device {name} ip {ip} mac {mac} action {a} enable {e}'
    cmd = cmd.format(name=dataobj.Name,ip=dataobj.IP,mac=dataobj.MAC,a=behave,e=dataobj.State)
    print "debug : " + cmd
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)    
#c 获取IP-MAC	test pass
@app.route('/ajax/data/rule/getIpMacConfig')
def getIpMacConfig():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    ip = req_get('ip')

    if (ip is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    retobj['data']=[]
    vtydirc = impl_ajax_getIpMacList(0)
    print vtydirc
    for eachdata in vtydirc['data']:
        if (eachdata['ip'] == ip):
            retobj['data'].append(eachdata)
    return jsonify(retobj)
#d 编辑IP-MAC	test pass
@app.route('/ajax/data/rule/setIpMacConfig')
def setIpMacConfig():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    data = req_get('data')
#debug
#    data = '{"Name": "d21", "IP": "3.3.3.3", "MAC": "03:66:FE:57:B4:90", "State": "1","Behave":"w" }'
#end
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)	
    dataobj = jstrtoobj(data)
    if dataobj.Behave=='0':
        behave = 'b'
    else:
        behave = 'w'
    cmd='ipmac edit device {name} ip {ip} mac {mac} action {a} enable {e}'
    cmd = cmd.format(name=dataobj.Name,ip=dataobj.IP,mac=dataobj.MAC,a=behave,e=dataobj.State)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)

#e 删除IP-MAC	test pass
@app.route('/ajax/data/rule/deleteIpMac')
def deleteIpMac():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    sids = req_get('sids')

    if (sids is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    ut = Util_telnet(promt)
    sids = sids.split(',')
    vtydirc = impl_ajax_getIpMacList(0)
    for eachip in sids:
        for eachdata in vtydirc['data']:
            if (eachdata['ip'] == eachip):
                cmd='ipmac del ip {ip}'.format(ip=eachdata['ip'])
                vtyret = ut.ssl_cmd(type,cmd)
                if (vtyret is None or vtyret.find('%')==0):
                    retobj['status'] = 0
                    retobj['message'] = 'vty failed'
                    return jsonify(retobj)
                continue
    retobj = vtyresul_to_obj(vtyret)
    return jsonify(retobj)



##################### 3 日志信息 ######################
#导出日志
def export_log(type,cmd,filename):
    retobj = {'status':1, 'message':'ok'}
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    if not os.path.exists('/download/'):
        retobj['status'] = 0
        retobj['message'] = '/download dir unexist'
        return jsonify(retobj)
    try:
        f = open('/download/'+filename,'w')
        for line in vtyret.split('\n'):
            f.write(line.replace('|',','))
        f.close()
    except:
        retobj['status'] = 0
        retobj['message'] = 'write file error'
        return jsonify(retobj)
    retobj['filename'] = filename
    return jsonify(retobj)
##################### 3.1 登录日志 ######################
# a 日志列表
@app.route('/ajax/data/log/getLoginList')
def getLoginList():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    page = req_get('page')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = 'show login_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 user * ip 0.0.0.0 state * content * pgindex 1 pgsize 2147483647'
    cmd = cmd.format(p=int(page))
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 6):
            continue
        jobj = {
                'data' : fields[1],
                'user':fields[3],
                'ip':fields[2],
                'status':fields[4],
                'reason':fields[5]
                }
        jrows.append(jobj)
    retobj['page'] = int(page)
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

# b 搜索日志列表
@app.route('/ajax/data/log/searchLoginList')
def searchLoginList():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    ip = req_get('ip')
    reason = req_get('reason')
    status = req_get('status')
    user = req_get('user')
    starttime = req_get('starttime')
    endtime = req_get('endtime')
    page = req_get('page')
    if ip=='':
        ip='0.0.0.0'
    if reason=='':
        reason='*'
    if status=='':
        status='*'
    if user=='':
        user='*'
    if starttime=='':
        starttime='1970-01-01/00:00:00'
    if endtime=='':
        endtime='2050-01-01/00:00:00'
    starttime = starttime.replace(' ','/')
    endtime = endtime.replace(' ','/')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = 'show login_log stime {st} etime {et} user {u} ip {i} state {s} content {c} pgindex {p} pgsize 10'
    cmd = cmd.format(st=starttime,et=endtime,u=user,i=ip,s=status,c=reason,p=int(page))
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 6):
            continue
        jobj = {
                'data' : fields[1],
                'user':fields[3],
                'ip':fields[2],
                'status':fields[4],
                'reason':fields[5]
                }
        jrows.append(jobj)
    retobj['page'] = int(page)
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

# c 导出日志
#/ajax/data/log/exportLogin
# d 导出日志路径
#/download/
@app.route('/ajax/data/log/exportLogin')
def exportLogin():
    type='inner'
    cmd = 'show login_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 user * ip 0.0.0.0 state * content * pgindex 1 pgsize 2147483647'
    filename = 'log_login.csv'
    return export_log(type,cmd,filename)

##################### 3.2 操作日志 ######################
# a 日志列表
@app.route('/ajax/data/log/getOperList')
def getOperList():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    page = req_get('page')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = 'show op_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 user * ip 0.0.0.0 op * type * pgindex 1 pgsize 2147483647'
    cmd = cmd.format(p=int(page))
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 6):
            continue
        jobj = {
                'data' : fields[1],
                'user':fields[3],
                'ip':fields[2],
                'behave':fields[4],
                'type':fields[5],
                'desc':field[6]
                }
        jrows.append(jobj)
    retobj['page'] = int(page)
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

# b 搜索日志列表
@app.route('/ajax/data/log/searchOperList')
def searchOperList():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    ip = req_get('ip')
    device = req_get('device')
    behave = req_get('behave')
    user = req_get('user')
    starttime = req_get('starttime')
    endtime = req_get('endtime')
    page = req_get('page')
    if ip=='':
        ip='0.0.0.0'
    if device=='':
        device='*'
    if behave=='':
        behave='*'
    if user=='':
        user='*'
    if starttime=='':
        starttime='1970-01-01/00:00:00'
    if endtime=='':
        endtime='2050-01-01/00:00:00'
    starttime = starttime.replace(' ','/')
    endtime = endtime.replace(' ','/')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = 'show op_log stime {st} etime {et} user {u} ip {i} op {op} type {t} pgindex {p} pgsize 10'
    cmd = cmd.format(st=starttime,et=endtime,u=user,i=ip,op=behave,t=device,p=int(page))
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 6):
            continue
        jobj = {
                'data' : fields[1],
                'user':fields[3],
                'ip':fields[2],
                'behave':fields[4],
                'type':fields[5]
                }
        jrows.append(jobj)
    retobj['page'] = int(page)
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

# c 导出日志
#/ajax/data/log/exportOper
# d 导出日志路径
#/download/
@app.route('/ajax/data/log/exportOper')
def exportOper():
    type='inner'
    cmd = 'show op_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 user * ip 0.0.0.0 op * type * pgindex 1 pgsize 2147483647'
    filename = 'log_operate.csv'
    return export_log(type,cmd,filename)

##################### 3.3 系统日志(内端机) ######################
# a 日志列表
@app.route('/ajax/data/log/getInnerList')
def getInnerList():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    page = req_get('page')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = 'show sys_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 module * level * content * pgindex {p} pgsize 10'
    cmd = cmd.format(p=int(page))
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 5):
            continue
        jobj = {
                'date' : fields[1],
                'model':fields[2],
                'class':fields[3],
                'content':fields[4]
                }
        jrows.append(jobj)
    retobj['page'] = int(page)
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

# b 搜索日志列表
@app.route('/ajax/data/log/searchInnerList')
def searchInnerList():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    module = req_get('module')
    level = req_get('class')
    content = req_get('keyword')
    starttime = req_get('starttime')
    endtime = req_get('endtime')
    page = req_get('page')
    if module=='':
        module='*'
    if level=='':
        level='*'
    if content=='':
        content='*'
    if starttime=='':
        starttime='1970-01-01/00:00:00'
    if endtime=='':
        endtime='2050-01-01/00:00:00'
    starttime = starttime.replace(' ','/')
    endtime = endtime.replace(' ','/')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = 'show sys_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 module {m} level {l} content {c} pgindex {p} pgsize 10'
    cmd = cmd.format(st=starttime,et=endtime,m=module,l=level,c=content,p=int(page))
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 5):
            continue
        jobj = {
                'date' : fields[1],
                'model':fields[2],
                'class':fields[3],
                'content':fields[4]
                }
        jrows.append(jobj)
    retobj['page'] = int(page)
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

# c 导出日志
#/ajax/data/log/exportInner
# d 导出日志路径
#/download/
@app.route('/ajax/data/log/exportInner')
def exportInner():
    type='inner'
    cmd = 'show sys_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 module * level * content * pgindex 1 pgsize 2147483647'
    filename = 'log_inner.csv'
    return export_log(type,cmd,filename)


##################### 3.3 系统日志(外端机) ######################
# a 日志列表
@app.route('/ajax/data/log/getOuterList')
def getOuterList():
    retobj = {'status':1, 'message':'ok'}
    type='outer'
    page = req_get('page')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = 'show sys_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 module * level * content * pgindex {p} pgsize 10'
    cmd = cmd.format(p=int(page))
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 5):
            continue
        jobj = {
                'date' : fields[1],
                'model':fields[2],
                'class':fields[3],
                'content':fields[4]
                }
        jrows.append(jobj)
    retobj['page'] = int(page)
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

# b 搜索日志列表
@app.route('/ajax/data/log/searchOuterList')
def searchOuterList():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    module = req_get('module')
    level = req_get('class')
    content = req_get('keyword')
    starttime = req_get('starttime')
    endtime = req_get('endtime')
    page = req_get('page')
    if module=='':
        module='*'
    if level=='':
        level='*'
    if content=='':
        content='*'
    if starttime=='':
        starttime='1970-01-01/00:00:00'
    if endtime=='':
        endtime='2050-01-01/00:00:00'
    starttime = starttime.replace(' ','/')
    endtime = endtime.replace(' ','/')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = 'show sys_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 module {m} level {l} content {c} pgindex {p} pgsize 10'
    cmd = cmd.format(st=starttime,et=endtime,m=module,l=level,c=content,p=int(page))
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 5):
            continue
        jobj = {
                'date' : fields[1],
                'model':fields[2],
                'class':fields[3],
                'content':fields[4]
                }
        jrows.append(jobj)
    retobj['page'] = int(page)
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

# c 导出日志
#/ajax/data/log/exportOuter
# d 导出日志路径
#/download/
@app.route('/ajax/data/log/exportOuter')
def exportOuter():
    type='outer'
    cmd = 'show sys_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 module * level * content * pgindex 1 pgsize 2147483647'
    filename = 'log_outer.csv'
    return export_log(type,cmd,filename)

##################### 3.3 系统日志(仲裁机) ######################
# a 日志列表
@app.route('/ajax/data/log/getArbiterList')
def getArbiterList():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    page = req_get('page')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = 'show sys_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 module * level * content * pgindex {p} pgsize 10'
    cmd = cmd.format(p=int(page))
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 5):
            continue
        jobj = {
                'date' : fields[1],
                'model':fields[2],
                'class':fields[3],
                'content':fields[4]
                }
        jrows.append(jobj)
    retobj['page'] = int(page)
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

# b 搜索日志列表
@app.route('/ajax/data/log/searchArbiterList')
def searchArbiterList():
    retobj = {'status':1, 'message':'ok'}
    type='inner'
    module = req_get('module')
    level = req_get('class')
    content = req_get('keyword')
    starttime = req_get('starttime')
    endtime = req_get('endtime')
    page = req_get('page')
    if module=='':
        module='*'
    if level=='':
        level='*'
    if content=='':
        content='*'
    if starttime=='':
        starttime='1970-01-01/00:00:00'
    if endtime=='':
        endtime='2050-01-01/00:00:00'
    starttime = starttime.replace(' ','/')
    endtime = endtime.replace(' ','/')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = 'show sys_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 module {m} level {l} content {c} pgindex {p} pgsize 10'
    cmd = cmd.format(st=starttime,et=endtime,m=module,l=level,c=content,p=int(page))
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 5):
            continue
        jobj = {
                'date' : fields[1],
                'model':fields[2],
                'class':fields[3],
                'content':fields[4]
                }
        jrows.append(jobj)
    retobj['page'] = int(page)
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

# c 导出日志
#/ajax/data/log/exportArbiter
# d 导出日志路径
#/download/
@app.route('/ajax/data/log/exportArbiter')
def exportArbiter():
    type='arbiter'
    cmd = 'show sys_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 module * level * content * pgindex 1 pgsize 2147483647'
    filename = 'log_arbiter.csv'
    return export_log(type,cmd,filename)

##################### 3.4 审计日志  ######################
# a 日志列表
@app.route('/ajax/data/log/getAuditList')
def getAuditList():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    page = req_get('page')
    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = 'show audit_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 user * proto * url * content * pgindex {p} pgsize 10'
    cmd = cmd.format(p=int(page))
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 6):
            continue
        jobj = {
                'date' : fields[1],
                'user':fields[2],
                'proto':fields[3],
                'url':fields[4],
                'keyword':fields[5]
                }
        jrows.append(jobj)
    retobj['page'] = int(page)
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

# b 搜索日志列表
@app.route('/ajax/data/log/searchAuditList')
def searchAuditList():
    retobj = {'status':1, 'message':'ok'}
    type='arbiter'
    url = req_get('url')
    keyword = req_get('keyword')
    proto = req_get('proto')
    user = req_get('user')
    starttime = req_get('starttime')
    endtime = req_get('endtime')
    page = req_get('page')
    if url=='':
        url='*'
    if keyword=='':
        keyword='*'
    if proto=='':
        proto='*'
    if user=='':
        user='*'
    if starttime=='':
        starttime='1970-01-01/00:00:00'
    if endtime=='':
        endtime='2050-01-01/00:00:00'

    if (page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    starttime = starttime.replace(' ','/')
    endtime = endtime.replace(' ','/')
    cmd = 'show audit_log stime {st} etime {et} user {u} proto {p} url {ur} content {c} pgindex {pg} pgsize 10'
    cmd = cmd.format(st=starttime,et=endtime,u=user,p=proto,ur=url,c=keyword,pg=int(page))
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 6):
            continue
        jobj = {
                'date' : fields[1],
                'user':fields[2],
                'proto':fields[3],
                'url':fields[4],
                'keyword':fields[5]
                }
        jrows.append(jobj)
    retobj['page'] = int(page)
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

# c 导出日志
#/ajax/data/log/exportAudit
# d 导出日志路径
#/download/
@app.route('/ajax/data/log/exportAudit')
def exportAudit():
    type='arbiter'
    cmd = 'show audit_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 user * proto * url * content * pgindex 1 pgsize 2147483647'
    filename = 'log_audit.csv'
    return export_log(type,cmd,filename)


##################### 4 事件信息 ######################
# 0 获取事件总数
def getEventNum(log_table):
    retobj = {'status':1, 'message':'ok'}

    event_total=0
    event_today=0

    ut = Util_telnet(promt)
    cmd = 'show_event_num table {log}'.format(log=log_table)
    type = 'inner'
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = vtyret.replace('\n','')
    vtyres = vtyret.split(',')
    event_total += int(vtyres[0].replace('total_num=',''))
    event_today += int(vtyres[1].replace('today_num=',''))

    type = 'outer'
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = vtyret.replace('\n','')
    vtyres = vtyret.split(',')
    event_total += int(vtyres[0].replace('total_num=',''))
    event_today += int(vtyres[1].replace('today_num=',''))

    type = 'arbiter'
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = vtyret.replace('\n','')
    vtyres = vtyret.split(',')
    event_total += int(vtyres[0].replace('total_num=',''))
    event_today += int(vtyres[1].replace('today_num=',''))

    return [event_total,event_today]

##################### 4.1 安全事件#####################
# a 事件列表
@app.route('/ajax/data/event/getSafeList')
def getSafeList():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    page = req_get('page')
    if (type is None or page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = 'show sec_event_log sip * dip * proto * stime * etime * pgindex {p} pgsize 10'
    cmd = cmd.format(p=page)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 9):
            continue
        jobj = {
                "id":int(fields[0]),
                "sourceIp": fields[2],
                "destIp": fields[3],
                "proto": fields[5],
                "date": fields[1],
                "riskLevel": int(fields[6]),
                "eventType": type
                }
        jrows.append(jobj)
    retobj['page'] = page
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

# b 搜索事件列表
@app.route('/ajax/data/event/searchSafeList')
def searchSafeList():
    retobj = {'status':1, 'message':'ok'}
    sourceIp = req_get('sourceIp')
    destIp = req_get('destIp')
    proto = req_get('proto')
    starttime = req_get('starttime')
    endtime = req_get('endtime')
    page = req_get('page')
    type = req_get('type')
    if (page is None or type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    if sourceIp=='':
        sourceIp='0.0.0.0'
    if destIp=='':
        destIp='0.0.0.0'
    if proto=='':
        proto='*'
    if starttime=='':
        starttime='1970-01-01/00:00:00'
    if endtime=='':
        endtime='2050-01-01/00:00:00'
    starttime = starttime.replace(' ','/')
    endtime = endtime.replace(' ','/')
    cmd = 'show sec_event_log sip {sip} dip {dip} proto {pr} stime {st} etime {et} pgindex {pg} pgsize 10'
    cmd = cmd.format(sip=sourceIp,dip=destIp,pr=proto,st=starttime,et=endtime,pg=page)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 9):
            continue
        jobj = {
                "id":int(fields[0]),
                "sourceIp": fields[2],
                "destIp": fields[3],
                "proto": fields[5],
                "date": fields[1],
                "riskLevel": int(fields[6]),
                "eventType": type
                }
        jrows.append(jobj)
    retobj['page'] = page
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)


# c 获取事件详情
@app.route('/ajax/data/event/getSafeConfig')
def getSafeConfig():
    retobj = {'status':1, 'message':'ok'}
    id = req_get('id')
    page = req_get('page')
    type = req_get('type')
    if (id is None or page is None or type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = 'show sec_event_log sip * dip * proto * stime * etime * pgindex {p} pgsize 10'
    cmd = cmd.format(p=page)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if (fields[0] != id):
            continue
        jobj = {
                "rule":int(fields[9]),
                "packSize": len(fields[8]),
                "packContent": fields[8],
                "proto": fields[5],
                "date": fields[1],
                "riskLevel": int(fields[6]),
                "eventType": type
                }
        break
    retobj['data'] = jrows
    return jsonify(retobj)


# d 清空所有事件
@app.route('/ajax/data/event/clearSafe')
def clearSafe():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    if (type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd='delete_log table sec_event_log'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    return jsonify(retobj)


# e 安全事件总数
app.route('/ajax/data/event/getEventNumSafe')
def getEventNumSafe():
    eventinfo =  getEventNum('sec_event_log')
    syseventinfo = {
        "totalEvent": eventinfo[0],
        "todaySysEvent": eventinfo[1]
    }
    retobj['syseventinfo'] = syseventinfo
    return jsonify(retobj)
# f 导出事件
@app.route('/ajax/data/event/exportSafe')
def exportSafe():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    if (type is None):
        retobj['status'] = 0
        retobj['message'] = 'input type error'
        return jsonify(retobj)
    cmd = 'show sec_event_log sip 0.0.0.0 dip 0.0.0.0 proto * stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 pgindex 1 pgsize 2147483647'
    filename = 'event_safe_'+type+'.csv'
    return export_log(type,cmd,filename)

##################### 4.2 系统事件#####################
#  a 事件列表
@app.route('/ajax/data/event/getSysList')
def getSysList():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    page = req_get('page')
    if (type is None or page is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd = 'show sys_event_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 content *  pgindex {p} pgsize 10'

    cmd = cmd.format(p=page)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 5):
            continue
        jobj = {
                "id":int(fields[0]),
                "date": fields[1],
                "eventClass": fields[2],
                "eventType": fields[3],
                "content": fields[4]
                }
        jrows.append(jobj)
    retobj['page'] = page
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

#  b 搜索事件列表
@app.route('/ajax/data/event/searchSysList')
def searchSysList():
    retobj = {'status':1, 'message':'ok'}
    content = req_get('content')
    starttime = req_get('starttime')
    endtime = req_get('endtime')
    page = req_get('page')
    type = req_get('type')
    if (page is None or type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    if content=='':
        content='*'
    if starttime=='':
        starttime='1970-01-01/00:00:00'
    if endtime=='':
        endtime='2050-01-01/00:00:00'
    starttime = starttime.replace(' ','/')
    endtime = endtime.replace(' ','/')
    cmd = 'show sys_event_log stime {st} etime {et} content {c}  pgindex {p} pgsize 10'
    cmd = cmd.format(st=starttime,et=endtime,c=content,pg=page)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    jrows = []
    totalline = '[,,]'
    for line in vtyret.split('\n'):
        fields = line.split('|')
        if len(fields)==1 and len(fields[0])>30:
            totalline = line
        if (len(fields) != 5):
            continue
        jobj = {
                "id":int(fields[0]),
                "date": fields[1],
                "eventClass": int(fields[2]),
                "eventType": int(fields[3]),
                "content": fields[4]
                }
        jrows.append(jobj)
    retobj['page'] = page
    retobj['total'] = get_total_num(totalline)
    retobj['data'] = jrows
    return jsonify(retobj)

# c 清空所有事件
@app.route('/ajax/data/event/clearSys')
def clearSys():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    if (type is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    cmd='delete_log table sys_event_log'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(type,cmd)
    if (vtyret is None or vtyret.find('%')==0):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    return jsonify(retobj)

#d 系统事件总数
app.route('/ajax/data/event/getEventNumSys')
def getEventNumSys():
    eventinfo = getEventNum('sys_event_log')
    safeeventinfo = {
        "totalEvent": eventinfo[0],
        "todaySafeEvent": eventinfo[1]
    }
    retobj['safeeventinfo'] = safeeventinfo
    return jsonify(retobj)

# f 导出事件
@app.route('/ajax/data/event/exportSys')
def exportSys():
    retobj = {'status':1, 'message':'ok'}
    type = req_get('type')
    if (type is None):
        retobj['status'] = 0
        retobj['message'] = 'input type error'
        return jsonify(retobj)
    cmd = 'show sys_event_log stime 1970-01-01/00:00:00 etime 2050-01-01/00:00:00 content * pgindex 1 pgsize 2147483647'
    filename = 'event_sys_'+type+'.csv'
    return export_log(type,cmd,filename)
##################### 7 用户登录 #####################
# 获取用户名密码，验证数据库登录，设置登录配置相关
@app.route('/ajax/data/user/checkUser')
def checkUser():
    retobj = {'status':2, 'message':'ok'}
    username = req_get('username')
    password = req_get('pw')
    remote_ip = request.remote_addr

    if (username is None or password is None):
        login_log.write_login_log(remote_ip,username,login_log.state[1],'unexist user')
        retobj['message'] = 'get input data error'
        retobj['status'] = 0
        return jsonify(retobj)

    if username=='root' and password=='admin@123':
        session_set('user', username)
        return jsonify(retobj)

    cmd = "select * from admin_table where user='{name}'".format(name=username)
    admin_list = get_sql_data('/etc/gap_sqlite3_db.conf',cmd)
    user_conf = get_sql_data('/etc/gap_sqlite3_db.conf',"select * from user_conf_table where id=1")

    if admin_list=='':
        login_log.write_login_log(remote_ip,username,login_log.state[1],'unexist user')
        retobj['message'] = 'username unexist!'
        retobj['status'] = 0
        return jsonify(retobj)
    else:
        admin_list = strtrim(admin_list)
        admin_list = admin_list.split('\n')
        admin = admin_list[0].split('|')
        sql_user = admin[1]
        sql_passwd = admin[2]
        sql_role = admin[3]
        sql_datelogin = admin[4]
        sql_loginerrtimes = int(admin[5])
    if user_conf=='':
        login_log.write_login_log(remote_ip,username,login_log.state[1],'user conf error')
        retobj['message'] = 'get sql user conf error'
        retobj['status'] = 0
        return jsonify(retobj)
    else:
        user_conf = strtrim(user_conf)
        user_conf = user_conf.split('\n')
        conf = user_conf[0].split('|')
        timelogout = int(conf[1])
        timestrylogin = int(conf[2])
    jrows = {
        "logouttime": 30,
        "userrole": sql_role,
        "username": sql_user
    }
    login_log = LoginObj()
    #密码字符匹配
    if password==sql_passwd:
        session_set('user', username)
        retobj['login_info'] = jrows
        login_log.write_login_log(remote_ip,username,login_log.state[0],'login success')
        return jsonify(retobj)
    else:
        sql_loginerrtimes += 1
        login_log.write_login_log(remote_ip,username,login_log.state[1],'passwd error')
        retobj['message'] = 'input user passwd error'
        retobj['status'] = 0
        return jsonify(retobj)

#----------------------------------------------------------add by zqzhang----------------------------------------------------------
#私有函数，获取total line
def __get_totalline(s):
    line = s.strip('[]')
    field = line.split(',')
    field = field[2].split('=')
    return field[1]

#私有函数，查询会话统计
def __select_session(proto,inip,outip,user,page,pagesize=10,mach='inner'):
    if (len(inip) == 0):
        inip = '0.0.0.0'
    if (len(outip) == 0):
        outip = '0.0.0.0'
    if (len(user) == 0):
        user = '*'
    retobj = {'page':1, 'data':[],'total':0}
    if (inip is None or outip is None or user is None or page is None):
        return retobj
    cmd='show session proto {p} user {u} sip {s} dip {d} pgindex {pi} pgsize {ps}'
    cmd = cmd.format(p=proto,u=user,s=outip,d=inip,pi=page,ps=pagesize)
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(mach, cmd)
    if (vtyret is None or vtyret.find('%')==0):
        return retobj      
    vtyret = strtrim(vtyret)
    jrows = []
    id=0
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if (len(fields) != 12):
            retobj['total'] = __get_totalline(line)
            continue 
        jobj = {
          'sessionId': fields[0],
          'name': fields[1],
          'state': fields[2],
          'date': fields[3],
          'outIp': fields[4],
          'outPort': fields[5],
          'inIp': fields[6],
          'inPort': fields[7],
          'outRecv': fields[8],
          'outSend': fields[9],
          'inRecv': fields[10],
          'inSend': fields[11]
                }
        id = id + 1
        jrows.append(jobj)
    retobj['data'] = jrows
    retobj['page'] = page
    return retobj

#查询所有HTTP会话
@app.route('/ajax/data/session/getHttpList')
def getHttpList():
    proto = 'HTTP'
    inip = '0.0.0.0'
    outip = '0.0.0.0'
    user = '*'
    page = req_get('page')
    retobj = __select_session(proto, inip, outip, user, page)
    return jsonify(retobj)


#按条件查询HTTP会话
@app.route('/ajax/data/session/searchHttpList')
def searchHttpList():
    proto = 'HTTP'
    inip = req_get('inip')
    outip = req_get('outip')
    user = req_get('user')
    page = req_get('page')
    retobj = __select_session(proto, inip, outip, user, page)
    return jsonify(retobj)

#查询所有FTP会话
@app.route('/ajax/data/session/getFtpList')
def getFtpList():
    proto = 'FTP'
    inip = '0.0.0.0'
    outip = '0.0.0.0'
    user = '*'
    page = req_get('page')
    retobj = __select_session(proto, inip, outip, user, page)
    return jsonify(retobj)

#按条件查询FTP会话
@app.route('/ajax/data/session/searchFtpList')
def searchFtpList():
    proto = 'FTP'
    inip = req_get('inip')
    outip = req_get('outip')
    user = req_get('user')
    page = req_get('page')
    retobj = __select_session(proto, inip, outip, user, page)
    return jsonify(retobj)

#查询所有TDCS会话
@app.route('/ajax/data/session/getTdcsList')
def getTdcsList():
    proto = 'TDCS'
    inip = '0.0.0.0'
    outip = '0.0.0.0'
    user = '*'
    page = req_get('page')
    retobj = __select_session(proto, inip, outip, user, page)
    return jsonify(retobj)

#按条件查询TDCS会话
@app.route('/ajax/data/session/searchTdcsList')
def searchTdcsList():
    proto = 'TDCS'
    inip = req_get('inip')
    outip = req_get('outip')
    user = req_get('user')
    page = req_get('page')
    retobj = __select_session(proto, inip, outip, user, page)
    return jsonify(retobj)

#查询所有HTTPS会话
@app.route('/ajax/data/session/getHttpsList')
def getHttpsList():
    proto = 'HTTPS'
    inip = '0.0.0.0'
    outip = '0.0.0.0'
    user = '*'
    page = req_get('page')
    retobj = __select_session(proto, inip, outip, user, page)
    return jsonify(retobj)

#按条件查询HTTPS会话
@app.route('/ajax/data/session/searchHttpsList')
def searchHttpsList():
    proto = 'HTTPS'
    inip = req_get('inip')
    outip = req_get('outip')
    user = req_get('user')
    page = req_get('page')
    retobj = __select_session(proto, inip, outip, user, page)
    return jsonify(retobj)

#获取系统时间和运行时间，（获取内端机系统时间即可，用来表示网闸的系统时间）
@app.route('/ajax/data/home/getSysTime')
def getSysTime():
    mach = 'inner'
    systime = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(time.time()))
    runtime = ''
    retobj = {'systime':systime, 'runtime':runtime}
    cmd='show status'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(mach, cmd)
    if (vtyret is None or vtyret.find('%')==0):
        return jsonify(retobj)       

    vtyret = strtrim(vtyret)
    for line in vtyret.split('\n'):
        fields = line.split('=')
        if (fields[0] == 'Time'):
            systime = fields[1]
        if (fields[0] == 'Runtime'):
            runtime = fields[1]

    retobj['systime'] = systime
    retobj['runtime'] = runtime
    return jsonify(retobj)    

#私有函数，获取指定机器的基础状态
def __get_machstate(mach):
    retobj = {'data':[{}]}
    cmd='show status'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(mach, cmd)
    if (vtyret is None or vtyret.find('%')==0):
        return jsonify(retobj) 

    vtyret = strtrim(vtyret)
    if (mach == 'arbiter'):
        totalevents = 0
        todayevents = 0
        for line in vtyret.split('\n'):
            fields = line.split('=')
            if (fields[0] == 'Cpu'):
                retobj['data'][0]['cpuState'] = fields[1]
            elif (fields[0] == 'Mem'):
                retobj['data'][0]['memoryState'] = fields[1]
            elif (fields[0] == 'Disk'):
                retobj['data'][0]['diskState'] = fields[1]      
            elif (fields[0] == 'Total-rules'):
                retobj['data'][0]['rulesNum'] = fields[1]
            elif (fields[0] == 'Ha-state'):
                retobj['data'][0]['deviceState'] = fields[1]
            elif (fields[0] == 'Service-state'):
                retobj['data'][0]['serviceState'] = fields[1]
            elif (fields[0] == 'Today-events'):
                todayevents = fields[1]
            elif (fields[0] == 'Total-events'):
                totalevents = fields[1]
            elif (fields[0] == 'User-rules'):
                retobj['data'][0]['authRuleNum'] = fields[1]
            elif (fields[0] == 'Ipmac-rules'):
                retobj['data'][0]['ipRuleNum'] = fields[1]

        retobj['data'][0]['todayEventNum'] = todayevents
        retobj['data'][0]['historyEventNum'] = int(totalevents) - int(todayevents)
    else:
        totalevents = '0'
        todayevents = '0'
        for line in vtyret.split('\n'):
            fields = line.split('=')
            if (fields[0] == 'Cpu'):
                retobj['data'][0]['cpuState'] = fields[1]
            elif (fields[0] == 'Mem'):
                retobj['data'][0]['memoryState'] = fields[1]
            elif (fields[0] == 'Disk'):
                retobj['data'][0]['diskState'] = fields[1]      
            elif (fields[0] == 'Total-rules'):
                retobj['data'][0]['rulesNum'] = fields[1]
            elif (fields[0] == 'Ha-state'):
                retobj['data'][0]['deviceState'] = fields[1]
            elif (fields[0] == 'Service-state'):
                retobj['data'][0]['serviceState'] = fields[1]
            elif (fields[0] == 'Today-events'):
                todayevents = fields[1]
            elif (fields[0] == 'Total-events'):
                totalevents = fields[1]
            elif (fields[0] == 'P0-state'):
                retobj['data'][0]['p0LinkState'] = fields[1]
            elif (fields[0] == 'P1-state'):
                retobj['data'][0]['p1LinkState'] = fields[1]     
            elif (fields[0] == 'P2-state'):
                retobj['data'][0]['p2LinkState'] = fields[1]
            elif (fields[0] == 'P3-state'):
                retobj['data'][0]['p3LinkState'] = fields[1] 
            elif (fields[0] == 'MGMT-state'):
                retobj['data'][0]['mgmtLinkState'] = fields[1]
            elif (fields[0] == 'HA-state'):
                retobj['data'][0]['haLinkState'] = fields[1] 

        retobj['data'][0]['todayEventNum'] = todayevents
        retobj['data'][0]['historyEventNum'] = int(totalevents) - int(todayevents)
        retobj['data'][0]['consoleLinkState'] = 1

    return retobj

#私有函数，获取指定机器的接口总流量值(历史流量)
def __get_traffic(mach):
    retobj = {'points':[],'timePoints':[]}

    cmd='show traffic'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(mach, cmd)
    if (vtyret is None or vtyret.find('%')==0):
        return retobj

    vtyret = strtrim(vtyret)
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        x = time.strftime("%H:%M:%S",time.localtime(int(fields[0])))
        retobj['timePoints'].append(x)
        y = round((float(fields[1])+float(fields[2]))*8/1000, 1)
        retobj['points'].append(y)
     
    return retobj

#私有函数，获取指定机器的接口总流量点值(当前流量)
def __get_traffic_point(mach):
    retobj = {}

    cmd='show status'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(mach, cmd)
    if (vtyret is None or vtyret.find('%')==0):
        return retobj

    vtyret = strtrim(vtyret)
    for line in vtyret.split('\n'):
        fields = line.split('=')
        up = 0.0
        down = 0.0
        if (fields[0] == 'traffic-up-bandwidth'):
            up = float(fields[1])
        elif (fields[0] == 'traffic-down-bandwidth'):
            down = float(fields[1])
        retobj['timePoint'] = time.strftime("%H:%M:%S",time.localtime(time.time()))
        retobj['point'] = round((up+down)*8/1000, 1)
    return retobj

#内端机接口总流量值查询
@app.route('/ajax/data/state/getTotalFlowInner')
def getTotalFlowInner():
    mach='inner'
    retobj = __get_traffic(mach)
    return jsonify(retobj)

#外端机接口总流量值查询
@app.route('/ajax/data/state/getTotalFlowOuter')
def getTotalFlowOuter():
    mach='outer'
    retobj = __get_traffic(mach)
    return jsonify(retobj)

#内端机接口总流量点值查询
@app.route('/ajax/data/state/getTotalFlowPointInner')
def getTotalFlowPointInner():
    mach='inner'
    retobj = __get_traffic_point(mach)
    return jsonify(retobj)

#外端机接口总流量点值查询
@app.route('/ajax/data/state/getTotalFlowPointOuter')
def getTotalFlowPointOuter():
    mach='outer'
    retobj = __get_traffic_point(mach)
    return jsonify(retobj)

#获取内端机的基础状态
@app.route('/ajax/data/state/getStateInner')
def getStateInner():
    mach='inner'
    retobj = __get_machstate(mach)
    return jsonify(retobj)

#获取外端机的基础状态
@app.route('/ajax/data/state/getStateOuter')
def getStateOuter():
    mach='outer'
    retobj = __get_machstate(mach)
    return jsonify(retobj)

#获取仲裁机的基础状态
@app.route('/ajax/data/state/getStateArbiter')
def getStateArbiter():
    mach='arbiter'
    retobj = __get_machstate(mach)
    return jsonify(retobj)

#获取内端机、外端机、仲裁机设备消息列表
@app.route('/ajax/data/device/getDeviceInfo')
def getDeviceInfo():
    mach = req_get('type')
    retobj = {'data':[{'devNo':'KED-U1200', 'devType':'', 'SN':'', 'version':''}]}

    cmd='show machinfo'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd(mach, cmd)
    if (vtyret is None or vtyret.find('%')==0):
        return jsonify(retobj) 

    vtyret = strtrim(vtyret)
    for line in vtyret.split('\n'):
        fields = line.split('=')
        if (fields[0] == 'devNo'):
            retobj['data'][0]['devNo'] = fields[1]
        elif (fields[0] == 'devType'):
            retobj['data'][0]['devType'] = fields[1]
        elif (fields[0] == 'SN'):
            retobj['data'][0]['SN'] = fields[1]      
        elif (fields[0] == 'version'):
            retobj['data'][0]['version'] = fields[1]

    return jsonify(retobj) 
#----------------------------------------------------------add by zqzhang----------------------------------------------------------
#---------------------------------------------------------add 2016.10.13-------------------------------------
#获取证书信息
@app.route('/ajax/data/device/getCertificatList')
def getCertificatList():
    retobj = {'data':[], 'total':2}
    root_crt = os.popen('openssl x509 -in /etc/openssl/private/ca.crt -inform pem -noout -text|grep "Subject:"|awk -F "=" \'{print $5}\'')
    root_crt_name = root_crt.read()
    root_crt_name = root_crt_name.strip('\n')
    local_crt = os.popen('openssl x509 -in /etc/openssl/certs/gap.crt -inform pem -noout -text|grep "Subject:"|awk -F "=" \'{print $5}\'')
    local_crt_name = local_crt.read()
    local_crt_name = local_crt_name.strip('\n')

    root_expire = os.popen('openssl x509 -in /etc/openssl/private/ca.crt -inform pem -noout -text|grep "Not After :"|awk -F ":" \'{print $2":"$3":"$4}\'')
    root_expire_time = root_expire.read()
    root_expire_time = root_expire_time.strip('\n')
    local_expire = os.popen('openssl x509 -in /etc/openssl/certs/gap.crt -inform pem -noout -text|grep "Not After :"|awk -F ":" \'{print $2":"$3":"$4}\'')
    local_expire_time = local_expire.read()
    local_expire_time = local_expire_time.strip('\n')

    x={'type':'root', 'name':root_crt_name, 'result':'ok', 'date':root_expire_time}
    retobj['data'].append(x)
    x={'type':'local', 'name':local_crt_name, 'result':'ok', 'date':local_expire_time}
    retobj['data'].append(x) 
    return jsonify(retobj) 

#证书更新
@app.route('/ajax/data/device/upgradeCertificat',methods=['post'])
def upgradeCertificat():
    retobj = {'status':0}

    f = request.files['file']
    if (f is None):
        return jsonify(retobj) 

    t = req_get('type')
    if (t is None):
        return jsonify(retobj) 

    cmd='rm -rf /tmp/cert_upgrade'
    os.system(cmd)
    cmd='mkdir -p /tmp/cert_upgrade'
    os.system(cmd)
    if (t == 'root'):
        tmp = '/tmp/cert_upgrade/root.crt'
    else:
        tmp = '/tmp/cert_upgrade/local.tar'
    f.save(tmp)

    if (t == 'root'):
        cmd='''vtysh -c 'configre termial' -c 'upgrade inner cacrt {0}'
            '''.format(tmp)
        os.popen(cmd)
        cmd='''vtysh -c 'configre termial' -c 'upgrade outer cacrt {0}'
            '''.format(tmp)
        os.popen(cmd)
    else:
        cmd='tar -xvf {src} -C /tmp/cert_upgrade'
        cmd = cmd.format(src=tmp)
        os.system(cmd)
        cmd='rm -rf {src}'
        cmd = cmd.format(src=tmp)
        os.system(cmd) 

        files = os.popen('ls /tmp/cert_upgrade/')
        files_name = files.read()
        files_name = strtrim(files_name)

        for f in files_name.split('\n'):
            if (4 == len(f and '.crt')):
                cmd='''vtysh -c 'configre termial' -c 'upgrade inner crt {0}'
                    '''.format(f)
                os.popen(cmd)
                cmd='''vtysh -c 'configre termial' -c 'upgrade outer crt {0}'
                    '''.format(f)
                os.popen(cmd) 
            elif (4 == len(f and '.key')):
                cmd='''vtysh -c 'configre termial' -c 'upgrade inner key {0}'
                    '''.format(f)
                os.popen(cmd)
                cmd='''vtysh -c 'configre termial' -c 'upgrade outer key {0}'
                    '''.format(f)
                os.popen(cmd)            

    retobj['status'] = 1
    return jsonify(retobj) 

#私有函数，获取rpm包的信息
def __get_rpm_info(rpm):
    cmd = '''rpm -qip {rpmfile} |grep "Name"|awk '{xxx}'
        '''.format(rpmfile=rpm,xxx='{print $3}')
    info = os.popen(cmd)
    name = info.read()
    name = strtrim(name)
    return name


#系统升级
@app.route('/ajax/data/device/upgradeSystem')
def upgradeSystem():
    dic_rpm = {'web':['inner'], \
            'pciehp':['arbiter'], \
            'is8u256a':['inner', 'outer'],\
            'engine-rsa':['inner','outer']}

    retobj = {'status':1}
    f = request.files['file']
    if (f is None):
        return jsonify(retobj) 

    cmd='rm -rf /tmp/gap_upgrade'
    os.system(cmd)
    cmd='mkdir -p /tmp/gap_upgrade'
    os.system(cmd)

    tmp = '/tmp/gap_upgrade'+ f.filename
    f.save(tmp)

    cmd='tar -xvf {src} -C /tmp/gap_upgrade'
    cmd = cmd.format(src=tmp)
    os.system(cmd)

    cmd='rm -rf {src}'
    cmd = cmd.format(src=tmp)
    os.system(cmd)

    files = os.popen('ls /tmp/gap_upgrade/')
    files_name = files.read()
    files_name = strtrim(files_name)

    for f in files_name.split('\n'):
        name = __get_rpm_info(f)
        if (name in dic_rpm.keys()):
            for i in dic_rpm[name]:
                cmd='''vtysh -c 'configre termial' -c 'upgrade {0} rpm {1}'
                '''.format(i, f)
                os.popen(cmd)
        else:
            cmd='''vtysh -c 'configre termial' -c 'upgrade outer rpm {0}'
                '''.format(f)
            os.popen(cmd)

            cmd='''vtysh -c 'configre termial' -c 'upgrade arbiter rpm {0}'
                '''.format(f)
            os.popen(cmd) 

            cmd='''vtysh -c 'configre termial' -c 'upgrade inner rpm {0}'
                '''.format(f)
            os.popen(cmd) 

    return jsonify(retobj) 

#恢复出厂设置
@app.route('/ajax/data/device/updateSystemRestore')
def updateSystemRestore():
    retobj = {'status':1}
    cmd='''vtysh -c 'configre termial' -c 'reset'
        '''
    os.popen(cmd) 
    return jsonify(retobj) 

#重启
@app.route('/ajax/data/device/updateSystemRestart')
def updateSystemRestart():
    retobj = {'status':0}
    retobj_ok = {'status':1}

    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd('outer', cmd)
    if (vtyret is None):
        return jsonify(retobj) 

    vtyret = ut.ssl_cmd('arbiter', cmd)
    if (vtyret is None):
        return jsonify(retobj) 

    os.system('reboot')      
    return jsonify(retobj_ok) 

#关机
@app.route('/ajax/data/device/updateSystemClose')
def updateSystemClose():
    retobj = {'status':0}
    retobj_ok = {'status':1}

    cmd='system poweroff'
    ut = Util_telnet(promt)
    vtyret = ut.ssl_cmd('outer', cmd)
    if (vtyret is None):
        return jsonify(retobj) 

    vtyret = ut.ssl_cmd('arbiter', cmd)
    if (vtyret is None):
        return jsonify(retobj) 

    os.system('poweroff')      
    return jsonify(retobj_ok) 
#---------------------------------------------------------add 2016.10.13-------------------------------------
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

