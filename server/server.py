import argparse
import asyncio
from asyncio import sleep
import json
import logging
import os
import ssl
import uuid
import time
import cv2
from aiohttp import web
from av import VideoFrame
from typing import Tuple
from objectDetection import objectDetection
import fractions
import threading

from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder, MediaRelay

# BBOX = '[{"label":"person","bbox":[206,46,1264,727],"score":0.88}]'

BBOX = None
OLDBBOX = None
CLICK = False
ROOT = os.path.dirname(__file__)
logger = logging.getLogger("pc")
pcs = set()
relay = MediaRelay()
VIDEO_CLOCK_RATE = 90000
VIDEO_PTIME = 1 / 30  # 30fps
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)
ok = None

tracker_types = ['BOOSTING', 'MIL','KCF', 'TLD', 'MEDIANFLOW', 'GOTURN', 'MOSSE', 'CSRT']
tracker_type = tracker_types[7] #tracker type

if tracker_type == 'BOOSTING':
    tracker = cv2.TrackerBoosting_create() #nie ma
if tracker_type == 'MIL':
    tracker = cv2.TrackerMIL_create()
if tracker_type == 'KCF':
    tracker = cv2.TrackerKCF_create()
if tracker_type == 'TLD':
    tracker = cv2.TrackerTLD_create()
if tracker_type == 'MEDIANFLOW':
    tracker = cv2.TrackerMedianFlow_create()
if tracker_type == 'GOTURN':
    tracker = cv2.TrackerGOTURN_create()
if tracker_type == 'MOSSE':
    tracker = cv2.TrackerMOSSE_create()
if tracker_type == "CSRT":
    tracker = cv2.TrackerCSRT_create() #aktualnie używany


initialized = False

class MediaStreamError(Exception):
    pass

class VideoTransformTrack(MediaStreamTrack):

    kind = "video"

    def __init__(self):
        super().__init__()  # don't forget this!

        video = cv2.VideoCapture()
        video.open(0, cv2.CAP_DSHOW)
        video.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        video.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.objectDetection = objectDetection()
        self.video = video

    async def next_timestamp(self) -> Tuple[int, fractions.Fraction]:
        if self.readyState != "live":
            raise MediaStreamError

        if hasattr(self, "_timestamp"):
            self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
            wait = self._start + (self._timestamp / VIDEO_CLOCK_RATE) - time.time()
            await asyncio.sleep(wait)
        else:
            self._start = time.time()
            self._timestamp = 0
        return self._timestamp, VIDEO_TIME_BASE

    async def recv(self):
        #BBOX = [{"label":"person","bbox":[206,46,1264,727],"score":0.88}]
        global CLICK
        global BBOX
        global ok
        global tracker
        global initialized

        pts, time_base = await self.next_timestamp()
        res, img = self.video.read()

        if CLICK:
            bbox = BBOX[0]['bbox']
            bbox = (bbox[0][0], bbox[0][1], bbox[1][0], bbox[1][1])
            print(bbox)
            ok = tracker.init(img, bbox)
            initialized = True
            CLICK = False
        if initialized:
            ok = res
            if not ok:
                print("Tracker init failed")
            else:
                ok, bbox = tracker.update(img)
                if ok:
                    cv2.putText(img, "Tracking", (100, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0,0,255), 2)
                    p1 = (int(bbox[0]), int(bbox[1]))
                    p2 = (int(bbox[0] + bbox[2]), int(bbox[1] + bbox[3]))
                    cv2.rectangle(img, p1, p2, (0,0,255), 2, 1)
                    BBOX[0]['bbox'] = [(int(bbox[0]), int(bbox[1])), (int(bbox[2]),int(bbox[3]))]
                    # print(BBOX)
                else:
                    cv2.putText(img, "Tracking failure detected", (100, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)
                    initialized = False
        else:
            img, detections = self.objectDetection.detection(img)
            BBOX = detections
            cv2.putText(img, "Detecting", (100, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)
            try:
                bbox = BBOX[0]['bbox']
                bbox = (bbox[0][0], bbox[0][1], bbox[1][0], bbox[1][1])
                p1 = (int(bbox[0]), int(bbox[1]))
                p2 = (int(bbox[0] + bbox[2]), int(bbox[1] + bbox[3]))
                cv2.rectangle(img, p1, p2, (0, 255, 0), 2, 1)
            except:
                pass
            # print(BBOX)
        # print(BBOX)
        frame = VideoFrame.from_ndarray(img, format="bgr24")
        frame.pts = pts
        frame.time_base = time_base
        return frame

async def index(request):
    content = open(os.path.join(ROOT, "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open(os.path.join(ROOT, "client.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)

async def css(request):
    content = open(os.path.join(ROOT, "styles.css"), "r").read()
    return web.Response(content_type="text/html", text=content)

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection()
    pc_id = "PeerConnection(%s)" % uuid.uuid4()
    pcs.add(pc)

    def log_info(msg, *args):
        logger.info(pc_id + " " + msg, *args)

    log_info("Created for %s", request.remote)

    video = VideoTransformTrack()
    video_sender = pc.addTrack(video)

    @pc.on("datachannel")
    def on_datachannel(channel):
        print(channel.label, "with id", channel.id, "-", "created by remote party")
        if channel.label == "chat":
            @channel.on("message")
            def on_message(message):
                log_info(str(message))
                log_info("chat")
                if isinstance(message, str):
                    try:
                        y = json.loads(message)
                        log_info(str(y))
                    except ValueError as e:
                        pass
        if channel.label == "joy":
            @channel.on("message")
            def on_message(message):
                log_info(str(message))
                log_info("joy")
                if isinstance(message, str):
                    try:
                        y = json.loads(message)
                        log_info(str(y))
                    except ValueError as e:
                        pass

        if channel.label == "bbox":
            @channel.on("message")
            def on_message(message):
                # global OLDBBOX
                # if BBOX != OLDBBOX:
                    if channel and BBOX is not None:
                        channel.send(str(BBOX))
                        OLDBBOX = BBOX

        if channel.label == "track":
            @channel.on("message")
            def on_message(message):
                global CLICK
                log_info(str(message))
                CLICK = True

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        log_info("Connection state is %s", pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)


    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)


    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="WebRTC audio / video / data-channels demo"
    )
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--record-to", help="Write received media to a file."),
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # if args.cert_file:
    #     ssl_context = ssl.SSLContext()
    #     ssl_context.load_cert_chain(args.cert_file, args.key_file)
    # else:
    ssl_context = None

    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/client.js", javascript)
    app.router.add_get("/styles.css", css)
    app.router.add_post("/offer", offer)
    web.run_app(
        app, access_log=None, host=args.host, port=args.port, ssl_context=None
    )



