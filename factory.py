from processor import TaskProcessor

class ManagerFactory:
    """
    Factory to ensure strict tenant isolation by creating
    new service instances per-request.
    """
    @staticmethod
    def get_processor(user_config):
        return TaskProcessor(user_config)
