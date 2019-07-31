function loadImages(){
    $('img[async-src]').each(
        function(){
            //* set the img src from data-src
            $(this).attr('src', $(this).attr('async-src'));
        }
    );
}


$(function() {
    loadImages();
    $.ajax({
        'url' : '/get_meteoblue',
        'type' : 'GET',
        'success' : function(data) {
            $("#metoblue_img").attr("src", data);
        }
    });
});
