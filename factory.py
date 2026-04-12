from processor import TaskProcessor

class ManagerFactory:
    """
    Factory to ensure strict tenant isolation by creating
    new service instances per-request.
    """
    @staticmethod
    def get_processor():
        return TaskProcessor()
