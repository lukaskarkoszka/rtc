// get DOM elements
var dataChannelLog = document.getElementById('data-channel'),
    iceConnectionLog = document.getElementById('ice-connection-state'),
    iceGatheringLog = document.getElementById('ice-gathering-state'),
    signalingLog = document.getElementById('signaling-state');

// peer connection
var pc = null;
var BBOX = null;

// data channel

var dc = null, dcInterval = null;

function createPeerConnection() {
    var config = {
        sdpSemantics: 'unified-plan'
    };

    if (document.getElementById('use-stun').checked) {
        config.iceServers = [{urls: ['stun:stun.l.google.com:19302']}];
    }

    pc = new RTCPeerConnection(config);

    // register some listeners to help debugging
    pc.addEventListener('icegatheringstatechange', function() {
        iceGatheringLog.textContent += ' -> ' + pc.iceGatheringState;
    }, false);
    iceGatheringLog.textContent = pc.iceGatheringState;

    pc.addEventListener('iceconnectionstatechange', function() {
        iceConnectionLog.textContent += ' -> ' + pc.iceConnectionState;
    }, false);
    iceConnectionLog.textContent = pc.iceConnectionState;

    pc.addEventListener('signalingstatechange', function() {
        signalingLog.textContent += ' -> ' + pc.signalingState;
    }, false);
    signalingLog.textContent = pc.signalingState;

    // connect audio / video
    pc.addEventListener('track', function(evt) {
        if (evt.track.kind == 'video')
            var video = evt.streams[0]
            document.getElementById('video').srcObject = video;
            var video  = document.getElementById('video');
            var canvas = document.getElementById('canvas');
            var ctx    = canvas.getContext('2d');

            function drawBbox(item, index) {
                ctx.beginPath();
                ctx.lineWidth = "2";
                ctx.strokeStyle = "blue";
                ctx.font = "30px Verdana";
                ctx.rect(item.bbox[0],item.bbox[1],item.bbox[2],item.bbox[3]);
                ctx.stroke();
                ctx.fillText(item.label,item.bbox[0], item.bbox[1]);
            }

            video.addEventListener('play', function () {
                var $this = this; //cache
                (function loop() {
                    if (!$this.paused && !$this.ended) {
                        if (!!BBOX){
                            ctx.canvas.width  = video.videoWidth;
                            ctx.canvas.height = video.videoHeight;
                            canvas.style.width = video.videoWidth;
                            canvas.style.height = video.videoHeight;
                            BBOX.forEach(drawBbox)
                        }
                        setTimeout(loop, 1000 / 30); // drawing at 30fps
                    }
                })();
            }, 0);

//        else
//            document.getElementById('audio').srcObject = evt.streams[0];
    });

    return pc;
}



function negotiate() {
    return pc.createOffer().then(function(offer) {
        return pc.setLocalDescription(offer);
    }).then(function() {
        // wait for ICE gathering to complete
        return new Promise(function(resolve) {
            if (pc.iceGatheringState === 'complete') {
                resolve();
            } else {
                function checkState() {
                    if (pc.iceGatheringState === 'complete') {
                        pc.removeEventListener('icegatheringstatechange', checkState);
                        resolve();
                    }
                }
                pc.addEventListener('icegatheringstatechange', checkState);
            }
        });
    }).then(function() {
        var offer = pc.localDescription;
        var codec;

        codec = document.getElementById('audio-codec').value;
        if (codec !== 'default') {
            offer.sdp = sdpFilterCodec('audio', codec, offer.sdp);
        }

        codec = document.getElementById('video-codec').value;
        if (codec !== 'default') {
            offer.sdp = sdpFilterCodec('video', codec, offer.sdp);
        }

        document.getElementById('offer-sdp').textContent = offer.sdp;
        return fetch('/offer', {
            body: JSON.stringify({
                sdp: offer.sdp,
                type: offer.type
            }),
            headers: {
                'Content-Type': 'application/json'
            },
            method: 'POST'
        });
    }).then(function(response) {
        return response.json();
    }).then(function(answer) {
        document.getElementById('answer-sdp').textContent = answer.sdp;
        return pc.setRemoteDescription(answer);
    }).catch(function(e) {
        alert(e);
    });
}
var space = 0;
window.onload = function(){
    var demo = document.getElementById('demo');
    var value = 0;
};

function start() {
    document.getElementById('start').style.display = 'none';

    pc = createPeerConnection();

    var time_start = null;

    function current_stamp() {
        if (time_start === null) {
            time_start = new Date().getTime();
            return 0;
        } else {
            return new Date().getTime() - time_start;
        }
    }

    if (document.getElementById('use-datachannel').checked) {
        //sendGamepadAxis
        dc = pc.createDataChannel('joy');
        dc.onclose = function() {
            clearInterval(dcInterval);
            dataChannelLog.textContent += '- close\n';
        };
            dc.onopen = function() {
                var gamepadObjStrOld
                window.addEventListener('gamepadconnected', (event) => {
                    dcInterval = setInterval(function() {
                        const update = () => {
                        let gamepadObj = {};
                        let axes = [];
                        gamepadObj.axes = axes;
                            for (const gamepad of navigator.getGamepads()) {
                                if (!gamepad) continue;
                                    for (const [index, axis] of gamepad.axes.entries()) {
                                        let value= (axis * 0.5 + 0.5)
                                        let axle = {
                                            index,
                                            value
                                        };
                                        gamepadObj.axes.push(axle);
                                    }
                            }
                         var gamepadObjStr = JSON.stringify(gamepadObj);
                        if (gamepadObjStr!= gamepadObjStrOld){
                            dc.send(gamepadObjStr);
                            gamepadObjStrOld = gamepadObjStr;
                            }
                        };
                        update();
                    }, 10);
                })
             };
        //GetBbox
        dc1 = pc.createDataChannel('bbox');
        dc1.onclose = function() {
            clearInterval(dcInterval);
            dataChannelLog.textContent += '- close\n';
        };

        dc1.onopen = function() {
            dcInterval = setInterval(function() {
                const update = () => {
                    dc1.send("getBbox");
                };
                update();
            }, 10);
        };

        dc1.onmessage = function(evt) {
            BBOX = JSON.parse(evt.data.replaceAll(/'/g, '"').replaceAll("(", "").replaceAll(")", ""));
            dataChannelLog.textContent = JSON.stringify(BBOX);
         }

        //track
        dc2 = pc.createDataChannel('track');
        dc2.onclose = function() {
            clearInterval(dcInterval);
            dataChannelLog.textContent += '- close\n';
        };


        dc2.onopen = function() {
            var canvas = document.getElementById('canvas');
            canvas.addEventListener("click", function(element) {
//                console.log(`mouse location = X: ${element.layerX}, Y: ${element.layerY}`)
                BBOX.forEach(bbox =>{
                    getSelectedBbox(bbox, element);
                });
            })

            function getSelectedBbox(bbox, element) {
              if (element.layerX > bbox.bbox[0] && element.layerX < bbox.bbox[2] && element.layerY > bbox.bbox[1] && element.layerY < bbox.bbox[3]){
                sendSelectedBbox(bbox)
              }
            }

            function sendSelectedBbox (selectedBbox){
                var selectedBoundingBox =  {"BBOX": [{"X": selectedBbox.bbox[0] + ',' + selectedBbox.bbox[1], "Y": selectedBbox.bbox[2] + ',' +selectedBbox.bbox[3]}]}
                var strSelectedBoundingBox = JSON.stringify(selectedBoundingBox);
                dc2.send(strSelectedBoundingBox);
                }
        };

    }

    var constraints = {
        audio: document.getElementById('use-audio').checked,
        video: true
    };

    if (constraints.audio || constraints.video) {
        if (constraints.video) {
            document.getElementById('media').style.display = 'block';
        }
        navigator.mediaDevices.getUserMedia(constraints).then(function(stream) {
            stream.getTracks().forEach(function(track) {
                pc.addTrack(track, stream);
            });
            return negotiate();
        }, function(err) {
            alert('Could not acquire media: ' + err);
        });
    } else {
        negotiate();
    }

    var canvas = document.querySelector('canvas');




    document.getElementById('stop').style.display = 'inline-block';
}

function stop() {
    document.getElementById('stop').style.display = 'none';

    // close data channel
    if (dc) {
        dc.close();
    }

    // close transceivers
    if (pc.getTransceivers) {
        pc.getTransceivers().forEach(function(transceiver) {
            if (transceiver.stop) {
                transceiver.stop();
            }
        });
    }

    // close local audio / video
    pc.getSenders().forEach(function(sender) {
        sender.track.stop();
    });

    // close peer connection
    setTimeout(function() {
        pc.close();
    }, 1000);
}

function sdpFilterCodec(kind, codec, realSdp) {
    var allowed = []
    var rtxRegex = new RegExp('a=fmtp:(\\d+) apt=(\\d+)\r$');
    var codecRegex = new RegExp('a=rtpmap:([0-9]+) ' + escapeRegExp(codec))
    var videoRegex = new RegExp('(m=' + kind + ' .*?)( ([0-9]+))*\\s*$')

    var lines = realSdp.split('\n');

    var isKind = false;
    for (var i = 0; i < lines.length; i++) {
        if (lines[i].startsWith('m=' + kind + ' ')) {
            isKind = true;
        } else if (lines[i].startsWith('m=')) {
            isKind = false;
        }

        if (isKind) {
            var match = lines[i].match(codecRegex);
            if (match) {
                allowed.push(parseInt(match[1]));
            }

            match = lines[i].match(rtxRegex);
            if (match && allowed.includes(parseInt(match[2]))) {
                allowed.push(parseInt(match[1]));
            }
        }
    }

    var skipRegex = 'a=(fmtp|rtcp-fb|rtpmap):([0-9]+)';
    var sdp = '';

    isKind = false;
    for (var i = 0; i < lines.length; i++) {
        if (lines[i].startsWith('m=' + kind + ' ')) {
            isKind = true;
        } else if (lines[i].startsWith('m=')) {
            isKind = false;
        }

        if (isKind) {
            var skipMatch = lines[i].match(skipRegex);
            if (skipMatch && !allowed.includes(parseInt(skipMatch[2]))) {
                continue;
            } else if (lines[i].match(videoRegex)) {
                sdp += lines[i].replace(videoRegex, '$1 ' + allowed.join(' ')) + '\n';
            } else {
                sdp += lines[i] + '\n';
            }
        } else {
            sdp += lines[i] + '\n';
        }
    }

    return sdp;
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); // $& means the whole matched string
}