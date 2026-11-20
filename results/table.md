| library | class | baseline B/inst | patched B/inst | heap reduction | throughput |
| --- | --- | ---: | ---: | ---: | ---: |
| starlette | `starlette.datastructures.URL` (public) | 148.7 | 124.5 | 16.3% | 0.990x |
| starlette | `starlette.datastructures.Secret` (public) | 80.7 | 48.5 | 39.9% | 1.008x |
| starlette | `starlette.routing.Host` (public) | 247.8 | 204.8 | 17.4% | 1.002x |
| starlette | `starlette.background.BackgroundTask` (public) | 168.7 | 136.5 | 19.1% | 0.998x |
| starlette | `starlette.authentication.AuthCredentials` (public) | 152.7 | 120.5 | 21.1% | 1.010x |
| more-itertools | `more_itertools.more.peekable` (public) | 984.7 | 952.5 | 3.3% | 1.067x |
| more-itertools | `more_itertools.more.seekable` (public) | 296.7 | 264.5 | 10.8% | 1.002x |
| more-itertools | `more_itertools.more.bucket` (public) | 440.7 | 408.5 | 7.3% | 0.998x |
| more-itertools | `more_itertools.more.countable` (public) | 224.7 | 192.5 | 14.3% | 1.014x |
| more-itertools | `more_itertools.more.time_limited` (public) | 288.7 | 256.5 | 11.1% | 1.014x |
| werkzeug | `werkzeug.datastructures.etag.ETag` (public) | 88.7 | 56.5 | 36.3% | 0.987x |
| werkzeug | `werkzeug.datastructures.etag.ETagSet` (public) | 528.7 | 496.5 | 6.1% | 0.994x |
| werkzeug | `werkzeug.datastructures.range.Range` (public) | 208.7 | 176.5 | 15.4% | 1.000x |
| werkzeug | `werkzeug.datastructures.range.ContentRange` (public) | 112.6 | 80.5 | 28.5% | 1.004x |
| werkzeug | `werkzeug.datastructures.range.IfRange` (public) | 88.7 | 56.5 | 36.3% | 1.006x |
| tomli | `tomli._parser.Flags` | 368.7 | 336.5 | 8.7% | 1.125x |
| tomli | `tomli._parser.NestedDict` | 144.7 | 112.5 | 22.2% | 0.976x |
| tomli | `tomli._parser.Output` | 585.0 | 488.5 | 16.5% | 1.020x |
| tomli | `tomli._parser.DEPRECATED_DEFAULT` | 72.7 | 40.5 | 44.3% | 1.001x |
