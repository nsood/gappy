#coding=utf-8  
from util_telnet import SystemStatus, Util_telnet, upgrade, interface_info
from util_telnet import changeIpaddr
from util_telnet import shortname, updateCa

from flask import Flask, request, render_template, make_response, session, redirect, jsonify
import json;
#import sqlite3
import time
from flask_cors import CORS
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

def telnet_call(cmd):
    s={}
    if (cmd == 'interface view'):
        ut = Util_telnet('GLCNS')
        s = ut.ssl_show_interface()
    return s


# 调用telnet，传入命令，返回字符串
#def telnet_call(cmd):
#    if (cmd == 'interface view'):
#        return 'P0  192.168.10.200  255.255.255.0  192.168.40.200  255.255.255.0  2.2.2.2\nP1  192.168.11.123  255.255.255.0  192.168.44.211  255.255.255.0  4.4.4.4\nP2  192.168.12.123  255.255.255.0  192.168.41.211  255.255.255.0  4.4.4.4\nP3  192.168.13.123  255.255.255.0  192.168.42.211  255.255.255.0  4.4.4.4'
#    if (cmd == 'route view'):
#        return '888 TCP 192.168.10.234 1111 P0 P1 33\n199 HTTP 192.168.10.234 1111 P0 P1 333\n122 HTTP 192.168.10.234 1111 P0 P3 888\n111 HTTP 192.168.10.234 1111 P0 P3 899\n123 HTTP 192.168.10.234 1111 P0 P3 801'
#    return None







##################### ajax call #####################

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



# 实现获取网卡信息
def impl_ajax_getNetworkList(filter):
    retobj = {'status':1, 'message':'ok'}

    vtyret = telnet_call('interface view')
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


#获取网卡列表
@app.route('/ajax/data/device/getNetworkList')
def route_ajax_getNetworkList():
    retobj = impl_ajax_getNetworkList(None)
    return jsonify(retobj)


#获取网卡信息
@app.route('/ajax/data/device/getNetworkConfig')
def route_ajax_getNetworkConfig():
    retobj = {'status':1, 'message':'ok'}

    id = req_get('id')
    if (id is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)

    retobj = impl_ajax_getNetworkList(id)
    return jsonify(retobj)


#设置网卡信息
@app.route('/ajax/data/device/setNetworkConfig')
def route_ajax_setNetworkConfig():
    retobj = {'status':1, 'message':'ok'}

    data = req_get('data')
    if (data is None):
        retobj['status'] = 0
        retobj['message'] = 'invalid request'
        return jsonify(retobj)
    
    reqobj = json.loads(data)
    return jsonify(retobj)


#获取路由列表
@app.route('/ajax/data/device/getRouterList')
def route_ajax_getRouterList():
    retobj = {'status':1, 'message':'ok'}

    vtyret = telnet_call('route view')
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)

    jrows = []
    for line in vtyret.split('\n'):
        fields = line.split(' ')
        if (len(fields) != 7):
            continue

        jobj = {
                'name':fields[0],
                'protocol':[fields[1]],
                'aimIp':fields[2],
                'aimPort':fields[3],
                'inFace':fields[4],
                'outFace':fields[5],
                'inPort':fields[6]
                }
        jrows.append(jobj)

    retobj['total'] = len(jrows)
    retobj['data'] = jrows
    return jsonify(retobj)



# 添加一个路由项
@app.route('/ajax/data/device/xxxx')
def route_ajax_addRouter():
    retobj = {'status':1, 'message':'ok'}
    cmd = 'route add routename {0} proto {1} dip {2} dport {3} outif {4} inif {5} inport {6}'
    cmd = cmd.format('11', '22', '33', '44', '55', '66', '77')

    vtyret = telnet_call(cmd)
    if (vtyret is None):
        retobj['status'] = 0
        retobj['message'] = 'vty failed'
        return jsonify(retobj)
    vtyret = strtrim(vtyret)
    
    retobj = vtyresul_to_obj(vtyret);
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

