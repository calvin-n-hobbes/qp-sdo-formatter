function toggle_visibility(divId) {
    var e = document.getElementById(divId);

    if ( e.style.display == 'block' ) {
        e.style.display = 'none';
    }
    else {
        e.style.display = 'block';
    }
}
