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

BBOX = None
ROOT = os.path.dirname(__file__)
logger = logging.getLogger("pc")
pcs = set()
relay = MediaRelay()
VIDEO_CLOCK_RATE = 90000
VIDEO_PTIME = 1 / 30  # 30fps
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)
class MediaStreamError(Exception):
    pass

class VideoTransformTrack(MediaStreamTrack):

    kind = "video"

    def __init__(self):
        super().__init__()  # don't forget this!

        video = cv2.VideoCapture(1)
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
        pts, time_base = await self.next_timestamp()
        res, img = self.video.read()
        global BBOX
        img, detection = self.objectDetection.detection(img)
        BBOX = detection
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


async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection()
    pc_id = "PeerConnection(%s)" % uuid.uuid4()
    pcs.add(pc)

    def log_info(msg, *args):
        logger.info(pc_id + " " + msg, *args)

    log_info("Created for %s", request.remote)

    # prepare local media
    player = MediaPlayer(os.path.join(ROOT, "demo-instruct.wav"))
    if args.record_to:
        recorder = MediaRecorder(args.record_to)
    else:
        recorder = MediaBlackhole()

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

        #works very slowly
        # def work(oldBbox):
        #     while True:
        #         if BBOX != oldBbox:
        #             if channel and BBOX is not None:
        #                 #channel.send(str(BBOX))
        #                 print(BBOX)
        #                 oldBbox = BBOX
        #
        # def sendBbox(oldBbox, loop):
        #     asyncio.set_event_loop(loop)
        #         asyncio.ensure_future(work(oldBbox))
        #         loop.run_forever()
        #     except KeyboardInterrupt:
        #         pass
        #     finally:
        #         print("Closing Loop")
        #         loop.close()
        #
        # if __name__ == "__main__":
        #     loop = asyncio.new_event_loop()
        #     x = threading.Thread(target=sendBbox, args=("", loop,))
        #     x.start()

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        log_info("Connection state is %s", pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        log_info("Track %s received", track.kind)

        if track.kind == "audio":
            pc.addTrack(player.audio)
            recorder.addTrack(track)
        elif track.kind == "video":
            pc.addTrack(
                VideoTransformTrack()
            )
            if args.record_to:
                recorder.addTrack(relay.subscribe(track))

    # @pc.on('track')
    # def on_track(track):
    #     if track.kind == 'video':
    #         local_video = VideoTransformTrack()
    #         pc.addTrack(local_video)
    #     @pc.on('datachannel')
    #     def on_datachannel(channel):
    #         @channel.on('message')
    #         def on_message(message):
    #             channel.send(str(local_video))

        @track.on("ended")
        async def on_ended():
            log_info("Track %s ended", track.kind)
            await recorder.stop()

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # # handle offer
    # await pc.setRemoteDescription(offer)
    # await recorder.start()
    #
    # # send answer
    # answer = await pc.createAnswer()
    # await pc.setLocalDescription(answer)

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
    app.router.add_post("/offer", offer)
    web.run_app(
        app, access_log=None, host=args.host, port=args.port, ssl_context=ssl_context
    )