// Map name → loading screen image from The Finals wiki
// Images sourced from https://www.thefinals.wiki/wiki/Arenas (CC BY-SA 4.0)
export const MAP_IMAGES: Record<string, string> = {
  Kyoto: "https://www.thefinals.wiki/w/images/c/c9/Kyoto_day.png",
  Bernal:
    "https://www.thefinals.wiki/w/images/6/62/Bernal_Standard_Afternoon.png",
  "Las Vegas Stadium":
    "https://www.thefinals.wiki/w/images/f/fa/Loading_Screen_Las_Vegas_Stadium_Afternoon.jpg",
  Monaco:
    "https://www.thefinals.wiki/w/images/a/a1/Monaco_Default_Afternoon.jpg",
  Nozomi: "https://www.thefinals.wiki/w/images/0/0e/NOZOMI_Placeholder.png",
  Citadel: "https://www.thefinals.wiki/w/images/0/0e/NOZOMI_Placeholder.png",
  Seoul: "https://www.thefinals.wiki/w/images/1/1e/Seoul_Default_Afternoon.jpg",
  "Skyway Stadium":
    "https://www.thefinals.wiki/w/images/7/7b/Skyway_Default_Afternnoon.jpg",
  Sys$Horizon:
    "https://www.thefinals.wiki/w/images/3/3a/Horizon_default_sunny_day.jpg",
  "Practice Range":
    "https://www.thefinals.wiki/w/images/8/8e/TestRange_Default.jpg",
  "Fortune Stadium":
    "https://www.thefinals.wiki/w/images/1/1b/Fortune_Stadium_Standard_Issue_Sunny_day.png",
  "P.E.A.C.E. Center":
    "https://www.thefinals.wiki/w/images/3/35/PEACE_Center_Day.png",
  "Fangwai City":
    "https://www.thefinals.wiki/w/images/6/68/Fangwai_City_Standard_Night.png",
  "Las Vegas":
    "https://www.thefinals.wiki/w/images/f/fc/Las-Vegas-2023_Loading-Screen.png",
};

export function getMapImage(mapName: string | undefined): string | undefined {
  if (!mapName) return undefined;
  return MAP_IMAGES[mapName];
}
