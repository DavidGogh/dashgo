#!/usr/bin/env python
# -*_ coding:utf-8 _*_

'''
publish:
    nav_cmd topic: output cmd for navigation
    beam_angle topic: out put wakeup angle
    aiui_msg
subscribe:
    curr_loc
    reset_beam
'''
import rospy
from std_msgs.msg import String, Int16
import roslib

import json
from serial import Serial
from serial.serialutil import SerialException
import thread
import time
import array
import gzip
from cStringIO import StringIO
import traceback


__author__ = 'Yuxiang Gao'
__copyright__ = 'Copyright (C) 2017 Yuxiang Gao'
__email__ = 'gaoyuxiang@stu.xjtu.edu.cn'
__license__ = 'GPL'
__version__ = '1.0'

AIUIAppid = '583c10e6'
AIUIKey = '2d8c2fa8a465b0dcbaca063e9493a2d9'
AIUIScene = 'main'


def json_load_byteified(file_handle):
    return _byteify(
        json.load(file_handle, object_hook=_byteify),
        ignore_dicts=True
    )


def json_loads_byteified(json_text):
    return _byteify(
        json.loads(json_text, object_hook=_byteify),
        ignore_dicts=True
    )


def _byteify(data, ignore_dicts=False):
    # if this is a unicode string, return its string representation
    if isinstance(data, unicode):
        return data.encode('utf-8')
    # if this is a list of values, return list of byteified values
    if isinstance(data, list):
        return [_byteify(item, ignore_dicts=True) for item in data]
    # if this is a dictionary, return dictionary of byteified keys and values
    # but only if we haven't already byteified it
    if isinstance(data, dict) and not ignore_dicts:
        return {
            _byteify(key,
                     ignore_dicts=True): _byteify(value, ignore_dicts=True)
            for key, value in data.iteritems()
        }
    # if it's anything else, return it in its original form
    return data


class aiui_msg_handler(object):  # 0x04
    """Handler for AIUI messages"""
    def __init__(self, jsonMsg):
        self.msgType = jsonMsg['type']
        # aiui_event: Result Error State Wakeup Sleep Vad;
        content = jsonMsg['content']
        if self.msgType == 'aiui_event':
            # print content.keys()
            eventType = content.get('eventType', None)
            arg1 = content.get('arg1', None)
            arg2 = content.get('arg2', None)
            info = content.get('info', None)
            result = content.get('result', None)
            if eventType == 1:  # EVENT_RESULT
                self.eventType = "eventResult"
                # self.info = self.content['info']
                # self.result = self.content['result']
                self.sub = info['data'][0]['params']['sub']
                if self.sub == 'iat':
                    # print jsonMsg
                    self.eventType = "eventResultIAT"
                    self.recogResult = [ws['cw'][0]['w']
                                        for ws in result['text']['ws']]
                elif self.sub is 'nlp':
                    self.recogResult = result.get('text', None)
            elif eventType == 2:  # EVENT_ERROR
                self.eventType = "eventError"
                self.errorCode = arg1
                self.errorMsg = info
            elif eventType == 3:  # EVENT_STATE
                self.eventType = "eventState"
                self.state = arg1
            elif eventType == 4:  # EVENT_WAKEUP
                self.eventType = "eventWakeup"
                self.info = content['info']
                self.angle = info['angle']
                self.beam = info['beam']
            elif eventType == 5:  # EVENT_SLEEP
                self.eventType = "eventSleep"
            elif eventType == 6:  # EVENT_VAD
                self.eventType = "eventVAD"
            elif eventType == 8:  # EVENT_CMD_RETURN
                self.eventType = "eventCmdReturn"
                self.cmdType = arg1
                self.isSuccess = (arg2 == 0)
                self.cmdInfo = info
            else:
                rospy.loginfo('Wrong input for aiui_event')
        elif self.msgType is 'wifi_status':
            self.wifiConnection = content['connected']
            self.ssid = content['ssid']
        elif self.msgType == 'tts_event':
            rospy.loginfo('tts_event')
            self.ttsStart = (True if (content['eventType'] == 0) else False)
            self.ttsError = content.get('error', None)
        else:
            rospy.loginfo('Not an aiui_event')

    def get_msg_type(self):
        """get event type -> String"""
        try:
            return self.msgType
        except:
            rospy.loginfo('msg type error for aiui_event')

    def get_type(self):
        """get event type -> String"""
        try:
            return self.eventType
        except:
            rospy.loginfo('type error for aiui_event')

    def get_angle(self):
        """get wakeup angle -> String"""
        try:
            return self.angle
        except:
            rospy.loginfo('no angle for aiui_event')

    def get_beam(self):
        """get wakeup beam -> int"""
        try:
            return self.beam
        except:
            rospy.loginfo('no beam for aiui_event')

    def get_result(self):
        """get iat result -> String"""
        try:
            return self.recogResult
        except:
            rospy.loginfo('no result for aiui_event')

    def get_error(self):
        """get error"""
        try:
            print ('error code : {0}, '
                   'error message : {1}').format(self.errorCode, self.errorMsg)
        except:
            rospy.loginfo('no error for aiui_event')

    def get_state(self):
        # get current state: STATE_IDLE, STATE_READY, STATE_WORKING
        try:
            return self.state
            print 'AIUI state: ' + self.state
        except:
            rospy.loginfo('no result for aiui_event')

    def get_tts_state(self):
        try:
            if self.ttsError is not None:
                rospy.loginfo('tts error: {}'.format(self.ttsError))
            return self.ttsStart
        except:
            rospy.loginfo('no state for tts_event')


class aiui_ctrl_msg(object):  # 0x05
    """Constructor for AIUI control messages"""
    def __init__(self, aiuiCtrlType, **content):
        self.aiuiType = aiuiCtrlType
        if aiuiCtrlType == 'aiui_msg':
            # e.g. aiui_ctrl_msg('aiui_msg', msg_type='reset')
            self.msgContent = {'msg_type': 0,
                               'arg1': 0,
                               'arg2': 0,
                               'params': ""}
            if content.get('msg_type', None) == 'state':
                self.msgContent['msg_type'] = 1
            elif content.get('msg_type', None) == 'reset':
                self.msgContent['msg_type'] = 4
            elif content.get('msg_type', None) == 'start':
                self.msgContent['msg_type'] = 5
            elif content.get('msg_type', None) == 'stop':
                self.msgContent['msg_type'] = 6
            elif content.get('msg_type', None) == 'reset_wakeup':
                self.msgContent['msg_type'] = 8
            elif content.get('msg_type', None) == 'set_beam':
                self.msgContent['msg_type'] = 9
                self.msgContent['arg1'] = content['arg1']
            elif content.get('msg_type', None) == 'set_params':
                self.msgContent['msg_type'] = 10
                self.msgContent['params'] = content['params']
            elif content.get('msg_type', None) == 'upload_lexicon':
                self.msgContent['msg_type'] = 11
                self.msgContent['params'] = content['params']
            elif content.get('msg_type', None) == 'send_log':
                self.msgContent['msg_type'] = 12
                self.msgContent['params'] = content['params']
            elif content.get('msg_type', None) == 'build_grammer':
                self.msgContent['msg_type'] = 16
                self.msgContent['params'] = content['params']
            elif content.get('msg_type', None) == 'update_local_lexicon':
                self.msgContent['msg_type'] = 17
                self.msgContent['params'] = content['params']
            else:
                rospy.loginfo('Wrong input for aiui_msg')
        elif aiuiCtrlType == 'voice':
            # e.g. aiui_ctrl_msg('aiui_msg', enable_voice=True)
            self.msgContent = {'enable_voice':
                               (False if (content.get('enable_voice', None)
                                is False) else True)}
        elif aiuiCtrlType == 'status':
            # e.g. aiui_ctrl_msg('status')
            self.msgContent = {'query': 'wifi'}
        elif aiuiCtrlType == 'save_audio':
            # e.g. aiui_ctrl_msg('save_audio', save_len=10)
            self.msgContent = {'save_len': content.get('save_len', 0)}
        elif aiuiCtrlType == 'tts':
            # e.g. aiui_ctrl_msg('tts', action='start', text='')
            if content['action'] == 'start':
                ttsMsg = {'action': 'start', 'text': content.get('text', None)}
            else:
                ttsMsg = {'action': 'stop'}
            self.msgContent = ttsMsg
        # elif aiuiCtrlType is 'handshake':
        #     self.msgContent = [165, 0, 0, 0]
        elif aiuiCtrlType == 'aiui_cfg':
            # e.g. aiui_ctrl_msg('aiui_cfg')
            self.msgContent = {'appid': AIUIAppid,
                               'key': AIUIKey,
                               'scene': AIUIScene,
                               'launch_demo': True}
        else:
            rospy.loginfo('ctrl_msg input error')

    def construct(self):
        """Construct JSON message for AIUI"""
        try:
            ctrlMsg = {'type': self.aiuiType,
                       'content': self.msgContent}
            rospy.loginfo('construct :' + json.dumps(ctrlMsg))
            return json.dumps(ctrlMsg)
        except:
            pass

    def construct_hex(self, msg_ID):
        """Construct hex message for AIUI"""
        t = array.array('B', [0xA5, 0x01,  # msg head & user ID
                              0x05,        # msg type
                              0x00, 0x00,  # msg length
                              0x00, 0x00   # msg ID
                              ])
        if self.aiuiType == 'aiui_cfg':
            t[2] = 0x03
        msg_ID += 1
        if msg_ID > 65535:
            msg_ID = 1
        t[5] = msg_ID & 0xff
        t[6] = (msg_ID >> 8) & 0xff
        # if self.type is 'handshake':
        #     t[2] = 0xff
        #     for d in self.construct():
        #         t.append(hex(d))
        # else:
        for ch in self.construct():
            t.append(ord(ch))
        msgLen = len(t) - 7
        t[3] = msgLen % 255
        t[4] = msgLen / 255
        t.append((~sum(t) + 1) & 0xff)
        rospy.loginfo(' '.join(format(b, '02x') for b in t.tolist()))
        return t


class AIUI_ROS:
    def __init__(self, name='AIUI_ROS'):
        self.globalID = 0
        self.sendCnt = 0
        self.ackID = 0
        self.handshakeID = 0
        self.handshakeIDLast = 1
        self.handshakeCnt = 0
        self.sendID = 0
        self.name = name

        rospy.init_node('AIUI_ROS', log_level=rospy.DEBUG)
        rospy.loginfo('Started AIUI node')
        # Cleanup when termniating the node
        rospy.on_shutdown(self.cleanup)

        # start serial port
        self.ser = Serial(port='/dev/xunfei',
                          baudrate=115200,
                          timeout=0.5)
        if self.ser is None:
            rospy.logerr('AIUI serial port init failed')

        # Overall loop rate
        self.rate = int(rospy.get_param("~rate", 20))
        r = rospy.Rate(self.rate)

        # start the message publisher
        self.aiuiPub = rospy.Publisher('aiui_msg', String, queue_size=10)
        rospy.loginfo('Started AIUI publisher')

        # start the cmd message publisher
        self.navCmd = rospy.Publisher('nav_cmd', String, queue_size=1)
        rospy.loginfo('Started nav_cmd publisher')

        # start the cmd message publisher
        self.beamAngle = rospy.Publisher('beam_angle', Int16, queue_size=1)
        rospy.loginfo('Started beam_angle publisher')

        # Subscribe to the curr_loc
        rospy.Subscriber('curr_loc', String, self.loc_callback)

        # Subscribe to the reset_beam
        rospy.Subscriber('reset_beam', Int16, self.reset_beam)

        # Subscribe to the robot_state topic to receive robot state info.
        rospy.Subscriber('robot_state', String, self.state_callback)

        # Reserve a thread lock
        self.mutex = thread.allocate_lock()

        self.keywords_to_command = {'stop': ['停止', '暂停', 'stop', 'halt'],
                                    'slower': ['减速', '慢行'],
                                    'faster': ['加速', '加快'],
                                    'forward': ['向前', '前进', '直行'],
                                    'backward': ['向后', '后退', '退后'],
                                    'rotate left': ['左旋'],
                                    'rotate right': ['右旋'],
                                    'turn left': ['左转', '向左'],
                                    'turn right': ['右转', '向右'],
                                    'quarter': ['quarter speed'],
                                    'half': ['half speed'],
                                    'full': ['full speed'],
                                    'pause': ['pause speech'],
                                    'continue': ['continue speech']}
        # Intro for each loaction
        self.TTSText = {'loc_0': '导航开始',
                        'loc_1': '这里是起始点',
                        'loc_2': '第一处停靠点八百标兵奔北坡',
                        'loc_3': '第二处停靠点北坡炮兵并排跑',
                        'loc_4': '第三处停靠点炮兵怕碰标兵标',
                        'loc_5': '第四处停靠点标兵怕碰炮兵炮',
                        'loc_6': '到达终点谢谢参观',
                        'end': '结束',
                        'timeout': '超时'}

        # Start receiving aiui serial
        while not rospy.is_shutdown():
            if self.ser is None:
                return
            # rospy.loginfo('%s starts' % (self.getName()))
            try:
                flag_read = self.ser.read()
                if(len(flag_read) > 0):
                    flag_read += self.ser.read(6)
                    if ((ord(flag_read[0]) == 165) and
                       (ord(flag_read[1]) == 1)):
                        # Recv data, flag is A5 01
                        dataLen = self.flagget_len(flag_read)
                        dataType = ord(flag_read[2])
                        self.msgID = self.flagget_id(flag_read)
                        rospy.logdebug('type:' + str(dataType))
                        rospy.logdebug('Len:' + str(dataLen))
                        rospy.logdebug('ID:' + str(self.msgID))
                        if (dataType == 1):  # handshaking message
                            data_read = self.ser.read(dataLen)
                            self.ser.read()
                            rospy.loginfo('handshaking message')
                            self.send_ok(flag_read, 0xff)
                        elif (dataType == 255):  # confirmation message
                            data_read = self.ser.read(dataLen)
                            self.ser.read()
                            rospy.loginfo('confirmation message')
                            self.handshakeID = self.msgID
                            self.handshakeCnt = 0
                        elif (dataType == 4 and
                              dataLen > 0 and
                              dataLen < 1024 * 1024):
                            rospy.loginfo('other message')
                            data_read = self.ser.read(dataLen)
                            self.ser.read()   # checkdata ,just read and pass
                            parsedMsg = self.parse_msg(flag_read, data_read)
                            print 'get one msg len=%d' % dataLen
            except SerialException:
                rospy.loginfo('serial.SerialException ERROR')
                rospy.loginfo(traceback.format_exc())
                self.ser.close()
                print 'serial closed'
                continue
        if self.ser.isOpen():
            self.ser.close()  # 串口关闭
        print "%s ends" % (self.getName())

    def getName(self):
        """return node name"""
        return self.name

    def get_command(self, data):
        """
        Attempt to match the recognized word or phrase to the
        keywords_to_command dictionary and return the appropriate
        command
        """
        for (command, keywords) in self.keywords_to_command.iteritems():
            for word in keywords:
                if word in data:
                    self.navCmd.publish(command)
                    return command

    def state_callback(self, data):
        self.robotState = data.data

    def loc_callback(self, data):
        """Callback function for subscription to current location"""
        currLoc = data.data
        rospy.loginfo('current location: %s', currLoc)
        self.send_tts('start', self.TTSText[currLoc])

    def reset_beam(self, data):
        msg = aiui_ctrl_msg('aiui_msg',
                            msg_type='set_beam',
                            arg1=str(data.data))
        self.mutex.acquire()
        self.ser.write(msg.construct_hex(self.globalID))
        rospy.loginfo('beam reset')
        self.mutex.release()

    def flagget_len(self, str):
        """Get AIUI message lenth"""
        return ord(str[3]) + ((ord(str[4])) << 8)

    def flagget_id(self, str):
        """Get AIUI message id"""
        return ord(str[5]) + ((ord(str[6])) << 8)

    def send_ok(self, str, msgflag):
        """Send handshake message"""
        rospy.loginfo('handsahkeCount:{}'.format(self.handshakeCnt))
        if self.handshakeCnt > 50:
            rospy.loginfo('handshake timeout')
            self.handshakeCnt = 0
            self.cleanup()
        # TODO: Merge send_ok with aiui_ctrl_msg
        # acm = aiui_ctrl_msg('handshake')
        # self.ser.write(acm.construct_hex(self.globalID))
        t = array.array('B', [0xA5, 0x01,   # msg head & user ID
                              msgflag,      # msg type
                              0x04, 0x00,   # msg length
                              0x00, 0x00,   # msg ID
                              0xA5, 0x00,   # handshaking msg
                              0x00, 0x00,   # handshaking msg
                              0x00])        # checksum
        if str is None:
            self.globalID += 1
            if self.globalID > 65535:
                self.globalID = 1
            t[5] = self.globalID & 0xff
            t[6] = (self.globalID >> 8) & 0xff
        else:
            t[5] = ord(str[5])
            t[6] = ord(str[6])
            self.globalID = t[5] + 255 * t[6]
        self.handshakeID = t[5] + 255 * t[6]
        if self.handshakeID == self.handshakeIDLast:
            self.handshakeCnt += 1
        else:
            self.handshakeCnt = 0
        self.handshakeIDLast = self.handshakeID
        t[11] = (~sum(t) + 1) & 0xff
        # rospy.loginfo(' '.join(format(b, '02x') for b in t.tolist()))
        self.ser.write(t)

    def send_tts(self, cmd, ttstxt):
        """Send TTS message"""
        acm = aiui_ctrl_msg('tts', action=cmd, text=ttstxt)
        rospy.loginfo('tts start: %s', ttstxt)
        print 'send_tts ID:' + str(self.globalID)
        self.mutex.acquire()
        self.ser.write(acm.construct_hex(self.globalID))
        self.mutex.release()
        rospy.loginfo('tts msg sent with id: %d', self.globalID)

    def parse_msg(self, flag, data):
        """Parse AIUI message"""
        # print 'getflag=%d' % ord(flag[2])
        if ord(flag[2]) == 0x4:  # AIUI message
            buf = StringIO(data)
            f = gzip.GzipFile(mode="rb", fileobj=buf)
            # loaded_json = json.loads(f.read())
            loadedJson = json_loads_byteified(f.read())
            # print loadedJson.keys()
            aiuiMsg = aiui_msg_handler(loadedJson)
            self.aiuiMsg = aiuiMsg
            # json_msg = json.dumps(loaded_json,
            #                       ensure_ascii=False,
            #                       sort_keys=True,
            #                       indent=4,
            #                       separators=(',', ': '))
            # print f.read()
            # print loaded_json
            # print json_msg
            # pprint(loaded_json)
            # MyPrettyPrinter().pprint(loadedJson)
            # rospy.loginfo(loadedJson)
            if aiuiMsg.get_msg_type() == 'aiui_event':
                if aiuiMsg.get_type() == 'eventWakeup':
                    self.beamAngle.publish(aiuiMsg.get_angle())
                    rospy.loginfo('wakeup angle: ' + str(aiuiMsg.get_angle()))
                elif aiuiMsg.get_type() == 'eventResultIAT':
                    rospy.loginfo('IAT result: ' +
                                  ''.join(aiuiMsg.get_result()))
                    # Check if there is command word in recognized result
                    command = self.get_command(''.join(aiuiMsg.get_result()))
            elif aiuiMsg.get_msg_type() == 'tts_event':
                if aiuiMsg.get_tts_state():
                    rospy.loginfo('tts start')
                elif not aiuiMsg.get_tts_state():
                    rospy.loginfo('tts end')
                else:
                    rospy.loginfo('tts state err')
            return aiuiMsg

    def cleanup(self):
    # On shutdown termiate serial
        if self.ser.isOpen():
            self.ser.close()
        print "%s ends" % (self.getName())


if __name__ == "__main__":
    try:
        AIUI_ROS()
        rospy.spin()
    except rospy.ROSInterruptException:
        rospy.loginfo("Voice navigation terminated.")
