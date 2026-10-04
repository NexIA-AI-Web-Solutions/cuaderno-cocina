import type {Plugin} from 'vite';

export function createBuildProvenance(options: {
    projectRoot: string;
    vueRoot: string;
    nodeModulesRoot: string;
    outDir: string;
}): {mainPlugin: Plugin; serviceWorkerPlugin: Plugin; finalizePlugin: Plugin};
