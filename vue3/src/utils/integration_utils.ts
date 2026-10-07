import brandMark from "@/assets/cuaderno-mark.svg";


export type Integration = {
    id: string,
    name: string,
    description: string,
    import: boolean,
    export: boolean,
    helpUrl: string,
    imgSrc?: string,
}

export const INTEGRATIONS: Array<Integration> = [
    {id: 'DEFAULT', name: "Cuaderno Cocina", description: "ZIP nativo con recetas, archivos e imágenes.", import: true, export: true, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#default', imgSrc: brandMark},
    {id: 'CHEFTAP', name: "Texto de recetas sin estructura", description: "Archivo de exportación con recetas en texto libre.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#cheftap'},
    {id: 'CHOWDOWN', name: "Markdown en carpetas", description: "Archivo con carpetas de recetas Markdown e imágenes.", import: true, export: true, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#chowdown'},
    {id: 'COOKBOOKAPP', name: "YAML de recetas", description: "Recetas .yml con ingredientes, instrucciones y propiedades.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#cookbook-manager'},
    {id: 'COOKLANG', name: "Texto con sintaxis .cook", description: "Archivos .cook con ingredientes y unidades dentro del texto.", import: true, export: true, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#cooklang'},
    {id: 'COOKMATE', name: "XML de ingredientes y tiempos", description: "Recetas XML con título, cantidades y tiempos de preparación.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#cookmate'},
    {id: 'COPYMETHAT', name: "HTML con listas de ingredientes", description: "Archivo recipes.html con listas de ingredientes e instrucciones.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#copymethat'},
    {id: 'DOMESTICA', name: "JSON de biblioteca con imágenes", description: "Lista JSON con instrucciones, ingredientes e imágenes integradas.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#domestica'},
    {id: 'MEALIE', name: "ZIP de recetas JSON · legado", description: "Backup anterior a v1 con archivos JSON por receta.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#mealie'},
    {id: 'MEALIE1', name: "Backup completo JSON · v1", description: "ZIP completo con database.json; admite planes y listas.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#mealie'},
    {id: 'MEALMASTER', name: "Texto en una columna · MMF", description: "Archivos .txt, .MMF o .MM con ingredientes en una columna.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#mealmaster'},
    {id: 'MELARECIPES', name: "JSON de receta con fotos", description: "Una receta JSON con imágenes codificadas dentro del archivo.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#mela'},
    {id: 'NEXTCLOUD', name: "ZIP de carpetas JSON", description: "Una carpeta por receta con recipe.json e imagen asociada.", import: true, export: true, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#nextcloud'},
    {id: 'OPENEATS', name: "JSON de modelos y relaciones", description: "Exportación JSON de modelos de recetas e ingredientes.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#openeats'},
    {id: 'PAPRIKA', name: "JSON comprimido de recetas", description: "Archivo de recetas comprimidas con JSON e imágenes integradas.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#paprika'},
    {id: 'PEPPERPLATE', name: "Texto de recetas en archivos", description: "ZIP con recetas en archivos .txt estructurados.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#pepperplate'},
    {id: 'PLANTOEAT', name: "Texto con campos y enlaces", description: "Recetas con campos Title, Ingredients y enlaces a fotografías.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#plan-to-eat'},
    {id: 'RECETTETEK', name: "JSON de listas y etiquetas", description: "Archivo recipes.json o recipes_0.json con la colección.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#recettetek'},
    {id: 'RECIPEKEEPER', name: "HTML de fichas de recetas", description: "Archivo recipes.html con bloques recipe-details.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#recipe-keeper'},
    {id: 'RECIPESAGE', name: "JSON-LD de recetas estructuradas", description: "Exportación JSON-LD con datos estructurados de recetas.", import: true, export: true, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#recipesage'},
    {id: 'REZKONV', name: "Texto de recetas delimitadas", description: "Recetas en texto con encabezados y bloques delimitados.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#rezkonv'},
    {id: 'SAFFRON', name: "Texto de ingredientes e instrucciones", description: "Recetas en texto con secciones de ingredientes y preparación.", import: true, export: true, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#safron'},
    {id: 'REZEPTSUITEDE', name: "XML con cabecera y pasos", description: "Recetario XML con título en la cabecera y pasos de preparación.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#rezeptsuitede'},
    {id: 'GOURMET', name: "XML de recetario", description: "Documento XML con una colección de recetas e ingredientes.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#gourmet'},
    {id: 'PESTLE', name: "JSON de ingredientes por secciones", description: "Colección JSON con ingredientes e instrucciones organizadas.", import: true, export: false, helpUrl: 'https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md#pestle'},
]
