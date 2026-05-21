import logging
import os


class PCDLogger:
    def __init__(self, name):
        self.logger = logging.getLogger(name)
        if self.logger.handlers:
            return

        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        current_dir = os.getcwd()
        log_dir = os.path.join(current_dir, '.ansible', 'logs')
        print(f"log directory seen: {current_dir}, {log_dir}")
        try:
            os.makedirs(log_dir, exist_ok=True)
            print(f"Directory created/exists: {log_dir}")
        except PermissionError as e:
            print(f"Permission denied creating directory {log_dir}: {e}")
            # Fallback to current directory
            log_dir = current_dir
            print(f"Falling back to current directory: {log_dir}")
        except Exception as e:
            print(f"Error creating directory {log_dir}: {e}")
            log_dir = current_dir
            print(f"Falling back to current directory: {log_dir}")

        log_fname = os.path.join(log_dir, 'pcd.log')
        print(f"Log file path: {log_fname}")

        try:
            fh = logging.FileHandler(log_fname)
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)
            print(f"File handler created successfully for: {log_fname}")
        except PermissionError as e:
            print(f"Permission denied creating log file {log_fname}: {e}")
        except Exception as e:
            print(f"Error creating file handler: {e}")

        # Create a console handler that will log all messages to the console
        try:
            ch = logging.StreamHandler()
            ch.setLevel(logging.DEBUG)
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)
            print("Console handler created successfully")
        except Exception as e:
            print(f"Error creating console handler: {e}")

    def debug(self, message):
        self.logger.debug(message)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)

    def critical(self, message):
        self.logger.critical(message)
