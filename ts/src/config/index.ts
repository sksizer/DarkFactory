type ConfigV1 = {
    sdlc: {
        // Standard SDLC 'slots' for configuring common tasks for the project
        slots: {
            dev: string,
            format: string,
            test: string,
            typecheck: string,
        }
    }
    workflow: {
        directories: string[]
    }
}

type Configuration = {
    v1: ConfigV1
}

export {};
