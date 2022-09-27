import json
import logging
import pickle
import signal
import sys
import time
from optparse import OptionParser
from threading import Thread
from typing import List, Dict, Tuple, Set

import websocket

from client.tcp_forward_client import TcpForwardClient
from common.logger_factory import LoggerFactory
from constant.message_type_constnat import MessageTypeConstant
from context.context_utils import ContextUtils
from entity.client_config_entity import ClientConfigEntity
from entity.message.message_entity import MessageEntity
from entity.message.push_config_entity import PushConfigEntity
from entity.message.tcp_over_websocket_message import TcpOverWebsocketMessage
from exceptions.duplicated_name import DuplicatedName

DEFAULT_CONFIG = './config_c.json'

DEFAULT_LOGGER_LEVEL = logging.INFO

name_to_level = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warn': logging.WARN,
    'error': logging.ERROR
}


def get_config() -> Tuple[ClientConfigEntity, Dict[str, Tuple[str, int]]]:
    name_to_addr: Dict[str, Tuple[str, int]] = dict()
    parser = OptionParser(usage="usage: %prog -c config_c.json -l info")
    parser.add_option("-c", "--config",
                      type='str',
                      dest='config',
                      default=DEFAULT_CONFIG,
                      help="config json file"
                      )
    parser.add_option("-l", "--level",
                      type='str',
                      dest='log_level',
                      default='info',
                      help="log level: debug, info, warn , error"
                      )
    (options, args) = parser.parse_args()
    log_level = options.log_level
    if log_level not in name_to_level:
        print('invalid log level.')
        sys.exit()
    ContextUtils.set_log_level(name_to_level[log_level])
    config_path = options.config
    with open(config_path, 'r') as rf:
        config_data: ClientConfigEntity = json.loads(rf.read())
    name_set: Set[str] = set()
    for client in config_data['client']:
        if client['name'] in name_set:
            raise DuplicatedName()
        name_set.add(client['name'])
        addr = (client['local_ip'], client['local_port'])
        name_to_addr[client['name']] = addr
    return config_data, name_to_addr


def on_message(ws, message: str):
    message_data: MessageEntity = pickle.loads(message)
    start_time = time.time()
    time_ = message_data['type_']
    if message_data['type_'] == MessageTypeConstant.WEBSOCKET_OVER_TCP:
        # LoggerFactory.get_logger().debug(f'get websocket message {message_data}')
        data: TcpOverWebsocketMessage = message_data['data']
        uid = data['uid']
        name = data['name']
        b = data['data']
        forward_client.create_socket(name, uid)
        forward_client.send_by_uid(uid, b)
    # LoggerFactory.get_logger().debug(f'on message {time_} cost time {time.time() - start_time}')


def on_error(ws, error):
    LoggerFactory.get_logger().error(f'error:  {error} ')


def on_close(ws, a, b):
    LoggerFactory.get_logger().info(f'close, {a}, {b} ')
    forward_client.close()


def on_open(ws):
    LoggerFactory.get_logger().info('open success')
    push_configs: List[PushConfigEntity] = config_data['client']
    message: MessageEntity = {
        'type_': MessageTypeConstant.PUSH_CONFIG,
        'data': push_configs
    }
    forward_client.is_running = True
    ws.send(pickle.dumps(message), websocket.ABNF.OPCODE_BINARY)
    task = Thread(target=forward_client.start_forward)
    task.start()


def signal_handler(sig, frame):
    print('You pressed Ctrl+C!')
    sys.exit(0)


if __name__ == "__main__":
    config_data, name_to_addr = get_config()
    signal.signal(signal.SIGINT, signal_handler)
    websocket.setdefaulttimeout(3)
    server_config = config_data['server']
    url = ''
    if server_config['https']:
        url += 'wss://'
    else:
        url += 'ws://'
    url += server_config['host'] + ":" + str(server_config['port']) + "/ws?password=" + server_config['password']
    ws = websocket.WebSocketApp(url,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close,
                                on_open=on_open)
    forward_client = TcpForwardClient(name_to_addr, ws)
    LoggerFactory.get_logger().info('start run_forever')
    while True:
        try:
            ws.run_forever()  # Set dispatcher to automatic reconnection
        except Exception as e:
            raise
        LoggerFactory.get_logger().info(f'try after 2 seconds')
        time.sleep(2)
