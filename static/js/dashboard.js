function loadImages(){
    var date = new Date();
    $('img[async-src]').each(
        function(){
            //* set the img src from async-src
            var new_src = $(this).attr('async-src') + '?_=' + date.getTime();
            $(this).attr('src', new_src);
        }
    );
}

function loadMeteoblue(){
    $.get('/get_meteoblue', function(data) {
        $("#metoblue_img").attr("src", data);
    });
}

function loadBluebikes(){
    var stations = [80, 184, 67];
    $.get('/get_bluebikes?station_ids=' + stations.join(','), function(data) {
        data = JSON.parse(data);
        stations.forEach(function (e) {
            $("#bb-"+ e + "-bikes").text(data[e]['num_bikes_available']);
            $("#bb-"+ e + "-docks").text(data[e]['num_docks_available']);
        });
    });
}

$(function() {
    loadMeteoblue();
    loadImages();
    loadBluebikes();
    setInterval(loadMeteoblue, 30*60*1000); // Refresh every 30 minutes
    setInterval(loadImages   , 10*60*1000); // Refresh every 10 minutes
    setInterval(loadBluebikes, 30*1000);    // Refresh every 30 seconds
});
