var amcp_url = "http://127.0.0.1:9731/amcp"
var commands = [
    "MIXER 1-90 FILL 0 0 .5 .5 25",
    "MIXER 1-90 FILL .5 0 .5 .5 25",
    "MIXER 1-90 FILL .5 .5 .5 .5 25",
    "MIXER 1-90 FILL  0 .5 .5 .5 25"
]

var i = 0

amcp = function(command){
    log("SENDING " + command)
    var xhr = new XMLHttpRequest()
    xhr.open('POST', amcp_url)
    xhr.responseType = "text"
    xhr.send(command)

    xhr.onload = function() {
        log("Status:" +  xhr.status + " : " + xhr.statusText)
        log(xhr.responseText)
    };

    xhr.onerror = function() {
        log("Request failed")
    }
}


play = function(){
    amcp("MIXER 1-90 CLEAR")
    amcp("PLAY 1-90 #ff0000 MIX 25")
}

update = function(data){
    var cmd = commands[i%4]
    amcp(cmd)
    i += 1
}

stop = function(){
    amcp("MIXER 1-90 CLEAR")
    amcp("CLEAR 1-90")
}