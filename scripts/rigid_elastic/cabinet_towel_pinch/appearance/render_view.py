"""Shared fixed view of the complete native motion."""


def camera_for(layout):
    location = layout['camera']
    target = layout['target']
    lens = layout['lens']
    if 'door_fold_cos' in layout:   # the open-door-rim reconstruction (the only current layout)
        # Include the floor landing while keeping the top of the door in view.
        target = [target[0], target[1], .3775]
        lens = 29.5
    return {'location_m': location, 'target_m': target, 'lens_mm': lens}
