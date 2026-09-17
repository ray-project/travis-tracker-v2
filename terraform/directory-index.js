// Resolve directory-style URLs to the index.html S3 actually stores.
//
// CloudFront's default_root_object only covers "/", and an S3 REST origin does
// no index-document resolution, so /nightly-release/ 404s even though Gatsby
// wrote public/nightly-release/index.html. Every route other than the site root
// is affected; it went unnoticed while the site was a single page at "/".
//
// Written for the cloudfront-js-1.0 runtime, which is ES5.1 — no endsWith(),
// no includes().
function handler(event) {
    var request = event.request;
    var uri = request.uri;

    if (uri.charAt(uri.length - 1) === '/') {
        request.uri = uri + 'index.html';
        return request;
    }

    // A last path segment with no dot is a route, not a file: /foo -> /foo/index.html.
    // Anything with an extension (/404.html, /app-abc123.js) is passed through, so
    // a genuine miss still reaches the 404 custom error response.
    var lastSegment = uri.substring(uri.lastIndexOf('/') + 1);
    if (lastSegment.indexOf('.') === -1) {
        request.uri = uri + '/index.html';
    }

    return request;
}
