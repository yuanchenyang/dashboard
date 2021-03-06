function getIDByAttr(attr){
    return $('[' + attr + ']').map(function () {
        return this.getAttribute(attr);
    }).get();
}

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
    var mb_img = $('#meteoblue_img');
    $.get('/get_meteoblue?url=' + mb_img.attr('mb_url'), function(data) {
        // Append time to force refresh
        // '#' will not cause error in meteoblue's url signature check
        mb_img.attr('src', data + '#' + new Date().getTime());
    });
}

function loadBluebikes(){
    var stations = getIDByAttr('bluebike_card_id');

    $.get('/get_bluebikes?station_ids=' + stations.join(','), function(data) {
        data = JSON.parse(data);
        stations.forEach(function (e) {
            $('#bb-'+ e + '-bikes').text(data[e]['num_bikes_available']);
            $('#bb-'+ e + '-docks').text(data[e]['num_docks_available']);
        });
    });
}

function loadWeather(){
    var stations = getIDByAttr('weather_station_card_id');

    stations.forEach(function(id){
        $.get($('[weather_station_card_id=\''+id+'\']').attr('url'),
              function(data) {
                  data = JSON.parse(data);
                  ['temp', 'humidity', 'wind'].forEach(function (param){
                      $('#ws-'+id+'-'+param).html(data[param]);
                  });
              });
    });
}

function loadNextbus(){
    var stops = getIDByAttr('nextbus_card_id');

    stops.forEach(function(id){
        $.get('/get_nextbus?stopid='+id,
              function(data) {
                  data = JSON.parse(data);
                  $('#nextbus-'+id+'-title')
                      .text(data['title']);
                  $('#nextbus-'+id+'-predictions')
                      .text(data['arrivals']);
              });
    });
}

function fullReload(){
    location.reload(true);
}

$(function() {
    loadMeteoblue();
    loadImages();
    loadWeather();
    loadBluebikes();
    loadNextbus();
    setInterval(fullReload   , 3*60*60*1000); // Full reload every 3 hours
    setInterval(loadMeteoblue, 30*60*1000);   // Refresh every 30 minutes
    setInterval(loadImages   , 10*60*1000);   // Refresh every 10 minutes
    setInterval(loadWeather  , 5*60*1000);    // Refresh every 5 minutes
    setInterval(loadNextbus  , 60*1000);      // Refresh every 1 minute
    setInterval(loadBluebikes, 30*1000);      // Refresh every 30 seconds
});
