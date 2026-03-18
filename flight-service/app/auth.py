import grpc
from app.config import settings


class ApiKeyServerInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, handler_call_details):
        metadata = dict(handler_call_details.invocation_metadata)
        api_key = metadata.get("x-api-key")
        if api_key != settings.api_key:
            def abort(request, context):
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid api key")
            return grpc.unary_unary_rpc_method_handler(abort)
        return continuation(handler_call_details)
