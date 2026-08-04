// Généré depuis ma-maison-portail-site/shared/energy-profile.json. Ne pas modifier à la main.
export const ENERGY_PROFILE = {
  "moonPhase": [
    "sensor.moon_phase",
    "sensor.phase_de_la_lune",
    "sensor.moon",
    "phase de la lune",
    "moon phase"
  ],
  "weatherCondition": [
    "weather.forecast_maison",
    "weather.escorpain",
    "météo maison",
    "forecast maison"
  ],
  "solarPower": [
    "sensor.onduleur_pv_power",
    "sensor.inverter_pv_power",
    "puissance solaire",
    "production solaire",
    "solar power",
    "pv power"
  ],
  "homePower": [
    "sensor.shellyem3_483fdac38616_channel_b_power",
    "sensor.onduleur_load_power",
    "sensor.inverter_load_power",
    "consommation maison",
    "puissance maison",
    "home power"
  ],
  "gridPower": [
    "sensor.shellyem3_483fdac38616_channel_c_power",
    "sensor.onduleur_grid_power",
    "sensor.inverter_grid_power",
    "sensor.1_2_3_home_puissance_reseau",
    "puissance reseau",
    "grid power"
  ],
  "gridImport": [
    "sensor.onduleur_today_energy_import",
    "grid import",
    "energie achetee"
  ],
  "gridExport": [
    "sensor.onduleur_today_energy_export",
    "injection reseau",
    "grid export",
    "energie exportee"
  ],
  "batteryLevel": [
    "sensor.onduleur_battery",
    "sensor.batterie_deye_soc",
    "sensor.inverter_battery",
    "niveau batterie",
    "batterie soc"
  ],
  "batteryPower": [
    "sensor.onduleur_battery_power",
    "sensor.inverter_battery_power",
    "sensor.1_2_3_home_puissance_batterie",
    "puissance batterie",
    "battery power"
  ],
  "pv1": [
    "sensor.onduleur_pv1_power",
    "pv1",
    "string 1"
  ],
  "pv2": [
    "sensor.onduleur_pv2_power",
    "pv2",
    "string 2"
  ],
  "pv3": [
    "sensor.onduleur_pv3_power",
    "pv3",
    "string 3"
  ],
  "dailyProduction": [
    "sensor.onduleur_today_production",
    "sensor.inverter_today_production",
    "sensor.1_2_3_home_daily_production",
    "production journaliere"
  ],
  "dailyConsumption": [
    "sensor.1_2_3_home_today_consumption",
    "sensor.onduleur_today_load_consumption",
    "sensor.inverter_today_load_consumption",
    "consommation journaliere"
  ],
  "dailyImport": [
    "sensor.onduleur_today_energy_import",
    "sensor.inverter_today_energy_import",
    "sensor.1_2_3_home_today_energy_import",
    "energie achetee aujourd hui"
  ],
  "dailyExport": [
    "sensor.onduleur_today_energy_export",
    "sensor.inverter_today_energy_export",
    "sensor.1_2_3_home_today_energy_export",
    "energie exportee aujourd hui"
  ],
  "monthlyProduction": [
    "sensor.1_2_3_home_monthly_production"
  ],
  "monthlyConsumption": [
    "sensor.1_2_3_home_monthly_consumption"
  ],
  "monthlyImport": [
    "sensor.1_2_3_home_monthly_import"
  ],
  "monthlyExport": [
    "sensor.1_2_3_home_monthly_export"
  ],
  "yearlyProduction": [
    "sensor.1_2_3_home_yearly_production"
  ],
  "yearlyConsumption": [
    "sensor.1_2_3_home_yearly_consumption"
  ],
  "yearlyImport": [
    "sensor.1_2_3_home_yearly_import"
  ],
  "yearlyExport": [
    "sensor.1_2_3_home_yearly_export"
  ],
  "totalProduction": [
    "sensor.onduleur_total_production",
    "sensor.inverter_total_production"
  ],
  "totalConsumption": [
    "sensor.shellyem3_483fdac38616_channel_b_energy"
  ],
  "totalImport": [
    "sensor.shellyem3_483fdac38616_channel_c_energy"
  ],
  "totalExport": [
    "sensor.shellyem3_483fdac38616_channel_c_energy_returned"
  ],
  "forecastToday": [
    "sensor.maison_energy_production_today",
    "sensor.energy_production_today",
    "prevision production aujourd hui"
  ],
  "forecastRemaining": [
    "sensor.maison_energy_production_today_remaining",
    "sensor.energy_production_today_remaining",
    "prevision production restante"
  ],
  "forecastPowerNow": [
    "sensor.maison_power_production_now",
    "sensor.power_production_now",
    "puissance solaire prevue maintenant"
  ],
  "cloudCover": [
    "sensor.escorpain_cloud_cover",
    "sensor.cloud_cover",
    "couverture nuageuse"
  ],
  "peakPower": [
    "sensor.pic_pv_jour"
  ],
  "installedPower": [
    "input_number.1_2_3_home_installed_solar_power",
    "sensor.1_2_3_home_installed_solar_power",
    "puissance installee"
  ]
} as const;
