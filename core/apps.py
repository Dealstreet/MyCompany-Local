from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        import os
        from . import utils
        import core.signals # Signals
        
        # Run only in main process (avoid double run with reloader)
        if os.environ.get('RUN_MAIN') == 'true':
            try:
                # utils.update_all_stocks()
                pass
            except Exception as e:
                print(f"Error updating stocks on startup: {e}")
