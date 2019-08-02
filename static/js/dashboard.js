function loadImages(){
    $('img[async-src]').each(
        function(){
            //* set the img src from data-src
            $(this).attr('src', $(this).attr('async-src'));
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
    loadImages();
    loadMeteoblue();
    loadBluebikes();
});
