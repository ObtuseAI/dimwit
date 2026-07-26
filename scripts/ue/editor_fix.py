import unreal
# LIVE fix on the currently-open editor level: real lumen-based light intensities (the prior unitless 6-22
# values were essentially zero) + permissive auto-exposure. Applies to live actors so the viewport updates now.
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LUM = unreal.LightUnits.LUMENS
pt = sp = 0
for a in eas.get_all_level_actors():
    cn = a.get_class().get_name()
    if cn == 'PointLight':
        c = a.get_component_by_class(unreal.PointLightComponent)
        c.set_editor_property('intensity_units', LUM); c.set_intensity(15000.0); c.set_attenuation_radius(3500.0); pt += 1
    elif cn == 'SpotLight':
        c = a.get_component_by_class(unreal.SpotLightComponent)
        c.set_editor_property('intensity_units', LUM); c.set_intensity(25000.0); c.set_attenuation_radius(3500.0); sp += 1
    elif cn == 'DirectionalLight':
        a.get_component_by_class(unreal.DirectionalLightComponent).set_intensity(6.0)
    elif cn == 'SkyLight':
        a.get_component_by_class(unreal.SkyLightComponent).set_intensity(2.0)
    elif cn == 'PostProcessVolume':
        s = a.get_editor_property('settings')
        s.set_editor_property('auto_exposure_method', unreal.AutoExposureMethod.AEM_HISTOGRAM)
        s.set_editor_property('override_auto_exposure_method', True)
        s.set_editor_property('auto_exposure_min_brightness', 0.05)
        s.set_editor_property('override_auto_exposure_min_brightness', True)
        s.set_editor_property('auto_exposure_max_brightness', 8.0)
        s.set_editor_property('override_auto_exposure_max_brightness', True)
        s.set_editor_property('auto_exposure_bias', 1.0)
        s.set_editor_property('override_auto_exposure_bias', True)
        a.set_editor_property('settings', s)
print(f"LIVEFIX pt={pt} sp={sp}")
