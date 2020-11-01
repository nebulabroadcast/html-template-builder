var ws_url = "ws://192.168.5.5:9001";
var tween = null;

play = function(){
    document.getElementById("container").style.visibility = "visible";
    if (tween){
        tween.play()
    } else {
        tween = gsap.from(".textline", {duration: 1, x: -100, opacity:0, stagger: .2});
    }
}

update = function(data){
    var params = parse_params(data)
    console.log(params);
    if ("f0" in params)
        document.getElementById("line1").innerText = params["f0"];
    if ("f1" in params)
        document.getElementById("line2").innerText = params["f1"];
}

stop = function(data){
    if (tween)
        tween.reverse();
}