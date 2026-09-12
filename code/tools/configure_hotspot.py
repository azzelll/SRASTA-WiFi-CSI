"""Generate private firmware configuration without printing credentials."""
import argparse
import json
import re
from pathlib import Path

def load_hotspot(path):
    config=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    ssid=config.get('ssid','');password=config.get('password','')
    channel=config.get('channel');sender=config.get('sender_mac','')
    if not isinstance(ssid,str) or not 1<=len(ssid.encode('utf-8'))<=32:
        raise ValueError('SSID must contain 1..32 UTF-8 bytes')
    if not isinstance(password,str) or not 8<=len(password.encode('utf-8'))<=63:
        raise ValueError('Hotspot password must contain 8..63 UTF-8 bytes')
    if type(channel) is not int or channel not in range(1,12):
        raise ValueError('Hotspot channel must be 1..11')
    if not isinstance(sender,str) or not re.fullmatch(r'[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}',sender):
        raise ValueError('Hotspot sender_mac must be the current BSSID')
    if any(c in ssid+password for c in ('\0','\r','\n')):
        raise ValueError('Control characters are not supported')
    return config

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=Path('artifacts/hotspot.local.json'));a=p.parse_args()
    c=load_hotspot(a.config)
    # JSON string escaping is valid C for these bounded WiFi strings. Local only.
    text='#pragma once\n#undef SRASTA_CHANNEL\n#undef SRASTA_TX_MAC\n'
    text+=f"#define SRASTA_CHANNEL {c['channel']}\n"
    text+='#define SRASTA_TX_MAC {'+','.join('0x'+part for part in c['sender_mac'].split(':'))+'}\n'
    text+='#define SRASTA_WIFI_SSID '+json.dumps(c['ssid'],ensure_ascii=False)+'\n'
    text+='#define SRASTA_WIFI_PASSWORD '+json.dumps(c['password'],ensure_ascii=False)+'\n'
    Path('firmware/include/srasta_hotspot.local.h').write_text(text,encoding='utf-8')
    print('Private hotspot header generated; credentials are hidden. Build rx_hotspot next.')
if __name__=='__main__':main()
