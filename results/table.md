| library | class | baseline B/inst | patched B/inst | heap reduction | throughput |
| --- | --- | ---: | ---: | ---: | ---: |
| starlette | `starlette.datastructures.URL` (public) | 148.7 | 140.5 | 5.5% | 1.046x |
| starlette | `starlette.datastructures.Secret` (public) | 80.7 | 64.5 | 20.0% | 1.019x |
| starlette | `starlette.routing.Host` (public) | 247.8 | 220.7 | 11.0% | 1.019x |
| starlette | `starlette.background.BackgroundTask` (public) | 168.7 | 152.5 | 9.6% | 1.006x |
| starlette | `starlette.authentication.AuthCredentials` (public) | 152.7 | 136.5 | 10.6% | 1.136x |
| more-itertools | `more_itertools.more.peekable` (public) | 984.7 | 968.5 | 1.6% | 0.941x |
| more-itertools | `more_itertools.more.seekable` (public) | 296.7 | 280.5 | 5.4% | 1.697x |
| more-itertools | `more_itertools.more.bucket` (public) | 440.7 | 424.5 | 3.7% | 0.986x |
| more-itertools | `more_itertools.more.countable` (public) | 224.7 | 208.5 | 7.2% | 0.986x |
| more-itertools | `more_itertools.more.time_limited` (public) | 288.7 | 272.5 | 5.6% | 1.003x |
| werkzeug | `werkzeug.datastructures.etag.ETag` (public) | 88.7 | 72.5 | 18.2% | 0.977x |
| werkzeug | `werkzeug.datastructures.etag.ETagSet` (public) | 528.7 | 512.5 | 3.1% | 1.017x |
| werkzeug | `werkzeug.datastructures.range.Range` (public) | 208.7 | 192.5 | 7.7% | 1.003x |
| werkzeug | `werkzeug.datastructures.range.ContentRange` (public) | 112.6 | 96.5 | 14.3% | 1.252x |
| werkzeug | `werkzeug.datastructures.range.IfRange` (public) | 88.7 | 72.5 | 18.2% | 1.074x |
| tomli | `tomli._parser.Flags` | 368.7 | 352.5 | 4.4% | 0.970x |
| tomli | `tomli._parser.NestedDict` | 144.7 | 128.5 | 11.2% | 0.999x |
| tomli | `tomli._parser.Output` | 585.0 | 536.5 | 8.3% | 1.000x |
| tomli | `tomli._parser.DEPRECATED_DEFAULT` | 72.7 | 56.5 | 22.3% | 1.033x |
