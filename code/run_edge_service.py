#!/usr/bin/env python3
"""Start SRASTA locally: explicit simulator, protected replay, or ESP32 serial."""
import argparse
from pathlib import Path
from srasta_csi.product import ProductRuntime
from srasta_csi.care_state import Policy
from srasta_csi.sources import SourceRunner
from srasta_csi.service import create_product_app
from srasta_csi.adapters import LocalAlarm,Notifications

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sources=p.add_mutually_exclusive_group(required=True)
    sources.add_argument('--demo',action='store_true')
    sources.add_argument('--replay',type=Path)
    sources.add_argument('--serial-port')
    p.add_argument('--db',type=Path,default=Path('artifacts/srasta-local.sqlite3'))
    p.add_argument('--model',type=Path)
    p.add_argument('--sender-mac')
    p.add_argument('--hotspot-config',type=Path)
    p.add_argument('--channel',type=int,default=1,choices=range(1,12))
    p.add_argument('--baud',type=int,default=921600)
    p.add_argument('--port',type=int,default=8000)
    p.add_argument('--host',choices=['127.0.0.1','localhost'],default='127.0.0.1')
    p.add_argument('--inactivity-seconds',type=float,default=120)
    p.add_argument('--confirmation-seconds',type=float,default=10)
    p.add_argument('--motion-threshold',type=float,default=.02)
    p.add_argument('--sudden-motion-threshold',type=float,default=.08)
    p.add_argument('--max-packet-gap-ms',type=float,help='Experimental rules only; models use their saved preprocessing')
    p.add_argument('--enable-notifications',action='store_true')
    p.add_argument('--gpio-pins',type=int,nargs=4,metavar=('BUZZER','GREEN','ORANGE','RED'))
    p.add_argument('--camera-model',type=Path)
    p.add_argument('--camera-index',type=int,default=0)
    args=p.parse_args()
    if args.hotspot_config:
        if not args.serial_port:
            p.error('--hotspot-config requires serial mode')
        from tools.configure_hotspot import load_hotspot
        c=load_hotspot(args.hotspot_config)
        args.sender_mac,args.channel=c['sender_mac'],c['channel']
    if args.serial_port and not args.sender_mac:
        p.error('--serial-port requires the configured TX --sender-mac')
    if args.replay and not args.replay.is_file():
        p.error('replay file is unavailable')
    if args.demo and (args.gpio_pins or args.enable_notifications or args.camera_model):
        p.error('simulator cannot activate physical outputs or external notifications')
    camera=None
    if args.camera_model:
        from srasta_csi.camera import EventCamera
        camera=EventCamera(args.camera_model,args.camera_index)
    source='simulator' if args.demo else ('replay' if args.replay else 'serial')
    runtime=ProductRuntime(args.db,source=source,demo=args.demo,model=args.model,sender=args.sender_mac,channel=args.channel,
        max_packet_gap_s=args.max_packet_gap_ms/1000 if args.max_packet_gap_ms is not None else None,
        policy=Policy(inactivity_s=args.inactivity_seconds,confirmation_s=args.confirmation_seconds,motion_threshold=args.motion_threshold,sudden_motion_threshold=args.sudden_motion_threshold),
        alarm=LocalAlarm(args.gpio_pins),notifications=Notifications(enabled=args.enable_notifications and source=='serial'),camera=camera)
    runner=SourceRunner(runtime,port=args.serial_port,baud=args.baud,replay=args.replay)
    if args.demo and runtime.machine.state != 'critical':
        runtime.simulate('standby')
    import uvicorn
    try:
        uvicorn.run(create_product_app(runtime,runner),host=args.host,port=args.port)
    finally:
        runtime.close()

if __name__=='__main__':
    main()
