"""Discover hidraw interfaces by explicitly registered USB identity."""
import glob
import os


def find_hidraw(models, errors):
    errors.clear()
    for sys_path in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        try:
            with open(os.path.join(sys_path, 'device', 'uevent'), encoding='ascii') as stream:
                identity = next((line[7:] for line in stream if line.startswith('HID_ID=')), '').strip()
            matches = [model for model in models if identity ==
                       f"0003:{model['usb']['vendor']}:{model['usb']['product']}"]
            if not matches:
                continue
            device_path = os.path.realpath(os.path.join(sys_path, 'device'))
            with open(os.path.join(os.path.dirname(device_path), 'bInterfaceNumber'), encoding='ascii') as stream:
                interface = stream.read().strip().lower().zfill(2)
            for model in matches:
                if interface == model['usb']['interface'].lower().zfill(2):
                    return model, '/dev/' + os.path.basename(sys_path)
        except (OSError, UnicodeError) as error:
            errors.append({'path': sys_path, 'error': str(error)})
    return None
