#!/usr/bin/python
'''
Created on 2015-9-9

@author: mfeng
'''
import os, ConfigParser
import re
import telnetlib
import time
import ssl
#from models import Uart

def shortname(path):
    while '/' in path:
        path = path[path.index('/')+1:]
    return path
class session_info:
    '''
    '''
    def __init__(self, id=0, status=0, ipaddr=None, port=None, connect_time=None, recv_bytes=0, send_bytes=0):
        self.id = id
        self.status = status
        self.ipaddr = ipaddr
        self.port = port
        self.connect_time = connect_time
        self.recv_bytes=recv_bytes
        self.send_bytes=send_bytes
    
    def parse(self, s):
        ss = s.split(',')
        if len(ss) == 8:
            self.id = int(ss[0])
            self.status = ss[1]
            self.ipaddr = ss[2]
            self.port = ss[3]
            self.connect_time =ss[4]
            self.recv_bytes=int(ss[5])
            self.send_bytes=int(ss[6])
            self.retry_send_bytes=int(ss[6])
        
        return len(ss)==8
        
class uart_info:
    def __init__(self, name=None):
        self.name = name
        self.recv_bytes = 0
        self.send_bytes = 0
    
    def parse(self, s):
        ss = s.split(',')
        if len(ss)==7:
            self.name = ss[0]
            self.recv_bytes=int(ss[1])
            self.recv_speed=(ss[2])
            self.max_recv_speed=(ss[3])
            self.send_bytes=int(ss[4])
            self.send_speed=(ss[5])
            self.max_send_speed=(ss[6])
            
        return len(ss)==7

class SystemStatus:
    def __init__(self):
        f = os.popen('acorn_eeprom read all')
        for line in f:
            s = re.findall(r'serialnum\s+:\s+([0-9A-Za-z]+)', line)
            if s and len(s) > 0:
                self.serialnumber=s[0]
            break
        self.product_code='GLCNS-1'
        self.systemtime = time.strftime('%Y-%m-%d %H:%M:%S')
        f = os.popen('uptime')
        for line in f:
            self.uptime = line
            break
        
        self.firmwareversion = 'Linux GLCNS 3.10.20-rt14-Cavium-Octeon'
        ut = Util_telnet('GLCNS')
        u= ut.show_version()
        if u and 'Version' in u.keys():
            self.softwareversion = u['Version']
        
        self.uarts = ut.uart_show_cfg()
        self.listen_port = ut.show_listen_port()
        
    def __str__(self):
        s = "serialnumber {0}".format(self.serialnumber)
        return s
class certObj:
    def __init__(self):
        self.certificate=''
        self.name=''
        self.index = 1;
        self.type=''
        self.builtIn=''
        self.caHashIx=''
        self.urlImportType=''
        self.dsc={}
                
class Util_telnet:
    def __init__(self, promt, host='192.168.10.201', port=2601):
        self.promt=promt
        self.host = host
        self.port = port
        self.tn = telnetlib.Telnet()
    
    def uart_show(self):
        rt = list()
        try:
            self.tn.open(self.host, self.port, 1)
        except Exception as e:
            print e
            return rt
        self.tn.read_until(self.promt+'>', 5)
        self.tn.write('enable\r')
        self.tn.read_until(self.promt+'#', 5)
        self.tn.write('show wml uart\r')
        s = self.tn.read_until(self.promt+'#',3)
        uarts = s.split('\n')
        for uart in uarts:
            u_info = uart_info()
            if(u_info.parse(uart)):
                rt.append(u_info)
        self.tn.close()
        return rt    
    
    def ssl_session_show(self):
        '''
        show all ssl session info
        '''
        rt = list()
        try:
            self.tn.open(self.host, self.port, 1)
        except Exception as e:
            return rt
        self.tn.read_until(self.promt+'>', 5)
        self.tn.write('enable\r')
        self.tn.read_until(self.promt+'#', 5)
        self.tn.write('show wml ssl session\r')
        s = self.tn.read_until(self.promt+'#',3)
        ssls = s.split('\n')
        for ssl in ssls:
            ss_info = session_info()
            if(ss_info.parse(ssl)):
                rt.append(ss_info)
        self.tn.close()
        return rt
 
    def ssl_show_interface(self):
        print 'ssl_show_interface in'
        rt = {}
        try:
            self.tn.open(self.host, self.port, 1)
        except Exception as e:
            return rt
        print 'read write in 1'
        self.tn.read_until(self.promt+'>', 5)
        self.tn.write('enable\r')
        print 'read write in 2'
        self.tn.read_until(self.promt+'#', 5)
        self.tn.write('configure terminal\r')
        print 'read write in 3'
        self.tn.read_until(self.promt+'(config)#', 5)
        self.tn.write('app\r')
        print 'read write in 4'
        self.tn.read_until(self.promt+'(app)#', 5)
        self.tn.write('interface view\r')
        print 'read write in 5'
        s = self.tn.read_until(self.promt+'(app)#', 5)
        return s
        return rt

       
    def ssl_cfg_get(self):
        rt={}
        try:
            self.tn.open(self.host, self.port, 1)
        except Exception as e:
            return rt
        self.tn.read_until(self.promt+'>', 5)
        self.tn.write('enable\r')
        self.tn.read_until(self.promt+'#', 5)
        self.tn.write('configure terminal\r')
        self.tn.read_until(self.promt+'(config)#', 5)
        self.tn.write('app\r')
        self.tn.read_until(self.promt+'(app)#', 5)
        self.tn.write('show ssl cfg\r')
        s = self.tn.read_until(self.promt+'(app)#', 5)
        ss = s.split('\n')
        for line in ss:
            if line.find('ca certificates') != -1:
                rt['root_ca']=line[line.find(':')+1:].strip()
            elif line.find('private certificates') != -1:
                rt['local_ca']=line[line.find(':')+1:].strip()
            elif line.find('private key') != -1:
                rt['private_key'] =  line[line.find(':')+1:].strip()
        return rt
    def ssl_ca_get(self):
        rt=list()
        
        calist = self.ssl_cfg_get()
        if 'root_ca' in calist.keys():
            cert = certObj()
            cert.name = shortname(calist['root_ca'])
            cert.index = 0
            cert.type = 'root'
            r = ssl_ca_parse(calist['root_ca'], True)
            if len(r) >0:
                cert.dsc = r[0]
            rt.append(cert)
        if 'local_ca' in calist.keys():
            cert = certObj()
            cert.name = shortname(calist['local_ca'])
            cert.type = 'local'
            r = ssl_ca_parse(calist['local_ca'], False)
            if len(r) >0:
                cert.dsc = r[0]
            rt.append(cert)
        return rt
    
    def show_log(self, action='head', cursor=0x0, nextcursor=0x0):
        try:
            self.tn.open(self.host, self.port, 1)
        except Exception as e:
            return []
        self.tn.read_until(self.promt+'>', 5)
        self.tn.write('enable\r')
        self.tn.read_until(self.promt+'#', 5)
        if action in ['head', 'tail']:
            self.tn.write('show log wml {0} 30\r'.format(action))
        else:
            print 'show log wml {0} offset {1} num 30 nextoffset {2}\r'.format(action, cursor, nextcursor)
            self.tn.write('show log wml {0} offset {1} num 30 nextoffset {2}\r'.format(action, cursor, nextcursor))
        s = self.tn.read_until(self.promt+'#', 5)
        ss= s.split('\n')
        ss.pop(0)
        cursor = ss.pop(0)
        nextcursor=ss.pop(0)
        ss.pop(-1)
        return cursor,nextcursor,ss
    
    def show_version(self):
        rt={}
        try:
            self.tn.open(self.host, self.port, 1)
        except Exception as e:
            return None
        self.tn.read_until(self.promt+'>', 5)
        self.tn.write('enable\r')
        self.tn.read_until(self.promt+'#', 5)
        self.tn.write('show version\r')
        s = self.tn.read_until(self.promt+'#', 5)
        ss = s.split('\n')
        for line in ss:
            rs=re.findall(r'([A-Za-z\s]+)\s+:\s+([0-9a-zA-z\.-]+)', line)
            if len(rs) > 0:
                rt[rs[0][0]]=rs[0][1]
        return rt
    
    def ntp_show(self):
        rt={}
        try:
            self.tn.open(self.host, self.port, 1)
        except Exception as e:
            return None
        self.tn.read_until(self.promt+'>', 5)
        self.tn.write('enable\r')
        self.tn.read_until(self.promt+'#', 5)
        self.tn.write('show ntp peer\r')
        s = self.tn.read_until(self.promt+'#', 5)
        ss = s.split('\n')
        for line in ss:
            rs=re.findall(r'ntp server is ([0-9a-zA-z\.-]+) interval ([0-9]+)', line)
            if len(rs) > 0:
                rt['ntp_server']=rs[0]
                rt['interval'] = rs[1]
        return rt
    
    def ntp_set(self, peer='', interval=0):
        try:
            self.tn.open(self.host, self.port, 1)
            self.tn.read_until(self.promt+'>', 5)
            self.tn.write('enable\r')
            self.tn.read_until(self.promt+'#', 5)
            self.tn.write('configure terminal\r')
            self.tn.write('ntp peer {0} interval {1}'.format(peer, interval))
        except Exception as e:
            return None
        pass
    
    def uart_show_cfg(self):
        r = list()
        try:
            self.tn.open(self.host, self.port, 1)
            self.tn.read_until(self.promt+'>', 5)
            self.tn.write('enable\r')
            self.tn.read_until(self.promt+'#', 5)
            self.tn.write('show uart cfg\r')
            s = self.tn.read_until(self.promt+'#', 5)
            ss = s.split('\n')
            for line in ss:
                if line.find('uart') >= 0:
                    continue
                u = Uart.parse(line)
                if u:
                    r.append(u)
        except Exception as e:
            return None
        
        return r
        pass
    def uart_set(self, name = 'S1', speed=115200, flow_cntl='no', databits=8, stopbits='1', parity='n'):
        try:
            self.tn.open(self.host, self.port, 1)
            self.tn.read_until(self.promt+'>', 5)
            self.tn.write('enable\r')
            self.tn.read_until(self.promt+'#', 5)
            self.tn.write('configure terminal\r')
            self.tn.write('app\r')
            self.tn.write('set uart {0}  speed {1} flow {2} databits {3} stopbits {4} parity {5}\r'.format(name, speed, flow_cntl, databits, stopbits, parity))
        except Exception as e:
            return None
        pass
    
    def uart_close(self, name):
        try:
            print name
            self.tn.open(self.host, self.port, 1)
            self.tn.read_until(self.promt+'>', 5)
            self.tn.write('enable\r')
            self.tn.read_until(self.promt+'#', 5)
            self.tn.write('configure terminal\r')
            self.tn.write('app\r')
            self.tn.write('close uart {0}\r'.format(name))
        except Exception as e:
            return None
        pass
    def show_listen_port(self):
        try:
            self.tn.open(self.host, self.port, 1)
            self.tn.read_until(self.promt+'>', 5)
            self.tn.write('enable\r')
            self.tn.read_until(self.promt+'#', 5)
            self.tn.write('show listen port\r')
            s = self.tn.read_until(self.promt+'#', 5)
            ss = s.split('\n')
            return ss[1]
        except Exception as e:
            return None
        pass
def ssl_ca_parse(filename, isroot=False):
    print filename
    if isroot:
        context = ssl.create_default_context()
        context.load_verify_locations(filename)
    
        return context.get_ca_certs(binary_form=False)
    else:
        l=[]
        rt={}
        f = open(filename)
        for line in f:
            if 'Version:' in line:
                rt['Version']=line[line.index(':')+1:]
            elif 'Serial Number:' in line:
                rt['Serial Number:']=line[line.index(':')+1:]
            elif 'Signature Algorithm:' in line:
                rt[' Signature Algorithm:']=line[line.index(':')+1:]
            elif 'Not After' in line:
                rt['notAfter']=line[line.index(':')+1:]
        l.append(rt)
        return l
    pass

def upgrade(filename):
    os.system('tar -zxf {0} -C /data/tmpfs'.format(filename))
    config = ConfigParser.RawConfigParser()
    config.read('/data/tmpfs/config.ini')
    sections = config.sections()
    
    if sections is None or len(sections) ==0 :
        print 'None section'
        return False
    print sections
    for section in sections:
        filename = config.get(section, 'name')
        checksum = config.get(section, 'checksum')
        shell_file=config.get(section, 'install')
        print filename
        if section == 'app':
            os.system('cd /data/tmpfs &&./{0}'.format(shell_file))
        elif section == 'image':
            os.system('mv /data/tmpfs/{0} /boot/'.format(filename))
            if os.access('/boot/{0}'.format(filename), os.F_OK) is True:
                os.system('echo 1 > /data/app_need_update')
                os.system('acorn_eeprom write bootfile {0}'.format(filename))
        elif section == 'www':
            os.system('tar -zxf /data/tmpfs/{0} -C /var/'.format(filename))
        else:
            return False
        
    return True

def interface_info():
    ret={}
    f = os.popen('ifconfig agl0')
    for line in f:
        if line.find('Link encap') > -1:
            s=re.findall(r'Link encap:([0-9a-zA-z]+)  HWaddr ([0-9a-fA-F:]+)', line[line.find('Link encap'):].strip())
            ret['Link encap']=s[0][0]
            ret['HWaddr']=s[0][1]
        elif 'inet addr' in line:
            s = re.findall(r'inet addr:([0-9\.]+)  Bcast:([0-9\.]+)  Mask:([0-9\.]+)', line[line.find('inet addr'):])
            ret['inet addr']=s[0][0]
            ret['Bcast']=s[0][1]
            ret['Mask']=s[0][2]
        elif 'inet6 addr' in line:
            s=re.findall(r'inet6 addr: ([0-9a-zA-Z:/]+) Scope:([0-9a-zA-Z]+)', line[line.find('inet6 addr'):])
            ret['inet6 addr']=s[0][0]
            ret['Scope']=s[0][1]
        elif 'MTU' in line:
            s = re.findall(r'MTU:([0-9]+)  Metric:([0-9]+)', line)
            ret['MTU'] = s[0][0]
            ret['Metric']=s[0][1]
        elif 'RX packets' in line:
            s = re.findall(r'RX packets:([0-9]+) errors:([0-9]+) dropped:([0-9]+) overruns:([0-9]+) frame:([0-9]+)', line[line.find('RX packets'):])
            ret['RX packets']=s[0][0]
            ret['RX errors']=s[0][1]
            ret['RX dropped']=s[0][2]
            ret['RX overruns']=s[0][3]
            ret['RX frame']=s[0][4]
        elif 'TX packets'in line:
            s=re.findall(r'TX packets:(\d+) errors:(\d+) dropped:(\d+) overruns:(\d+) carrier:(\d+)', line[line.find('TX packets'):])
            ret['TX packets']=s[0][0]
            ret['TX errors']=s[0][1]
            ret['TX dropped']=s[0][2]
            ret['TX overruns']=s[0][3]
            ret['TX frame']=s[0][4]
        elif 'RX bytes' in line:
            s=re.findall(r'RX bytes:([0-9]+)\s+(\([0-9\.]+ [KM]b\))\s+TX bytes:([0-9]+)\s+(\([0-9\.]+ [KM]b\))', line[line.find('RX bytes'):])
            ret['RX bytes']=s[0][0]
            ret['RX bytes Mb']=s[0][1]
            ret['TX bytes']=s[0][2]
            ret['TX bytes Mb']=s[0][3]
    
    ret['Name']='agl0'
    ret['Status']='UP'
    ret['Type']='Static'
    f = os.popen('/usr/bin/set_if.sh status')
    for line in f:
        if line.find('dhcp') >= 0:
            ret['Type']='DHCP'
    return ret

def changeIpaddr(interface, ip_type, ipaddr, mask, gw):
    if ip_type == 1:
        os.system('/usr/bin/set_if.sh dhcp')
    else:
        os.system('/usr/bin/set_if.sh static {0} {1} {2}'.format(ipaddr, mask, gw))

def updateCa(old, new):
    os.system('cp {0} /data/{1}.{2}'.format(old, shortname(old),time.strftime('%Y%m%d%H%M%S')))
    os.system('mv {0} {1}'.format(new, old))
    pass
if __name__ == '__main__':
    interface_info()
    ut = Util_telnet()
    s= SystemStatus()
    print s
    r = ut.uart_show('GLCNS')
    for i in r:
        print r
    print ut.show_version('GLCNS')
    print ut.ntp_show('GLCNS')
    
    print '/etc/openssl/private/server_ca.crt'
    ca = ssl_ca_parse('/etc/openssl/private/server_ca.crt', True)
    for k in ca:
        print k
    ca = ssl_ca_parse('/etc/openssl/certs/server.crt', False)
    for k in ca:
        print k
