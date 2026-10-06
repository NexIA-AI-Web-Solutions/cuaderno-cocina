(function () {
    // Configuration stays in the invoking bookmarklet's closure, never site storage.
    window.cuadernoBookmarklet = function (config) {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', config.url, true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.setRequestHeader('Authorization', 'Bearer ' + config.token);
        xhr.onload = () => {
            if (xhr.readyState === 4 && xhr.status === 201) {
                const redirect = new URL(config.redirect);
                redirect.searchParams.set('bookmarklet_import', JSON.parse(xhr.response).id);
                window.open(redirect.href);
            } else {
                console.error('Error!');
            }
        };
        xhr.send(JSON.stringify({
            url: window.location.protocol + '//' + window.location.host + window.location.pathname,
            html: document.documentElement.outerHTML,
        }));
    };
})();
