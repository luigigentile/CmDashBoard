export const prova = {
    // initial state
    state: {
        nome: "",
    },
}


export const dashboard = {
    // initial state
    state: {
        count: 0,
        categorySelected :"Part",
        historyCategorySelected:[],
        subCategorySelected:"",
        minManufacturerCount : 8,
        allBlock: [],
        countBlockType : [],
        sons :[]
    },
    reducers: {
        // handle state changes with pure functions
     
        setHistoryCategorySelected(state, payload) {
            return {
                ...state,
                historyCategorySelected: payload
            }
        },

        setCategorySelected(state, payload) {
            return {
                ...state,
                categorySelected: payload
            }
        },

        setSubCategorySelected(state, payload) {
            return {
                ...state,
                subCategorySelected: payload
            }
        },

        setMinManufacturerCount(state, payload) {
            return {
                ...state,
                minManufacturerCount: payload
            }
        },

        
        setSons(state, payload) {
            console.log("aggiorno sons")
            return {
                ...state,
                sons: payload
            }
        },
        
        increment(state, increment) {
            console.log('we are here')
            console.log(increment)
            return {
                ...state,
                count: state.count + increment
            }
        },
        
        loadAllBlock(state, payload) {
            return {
                ...state,
                allBlock: payload
            }
        },

        loadCountBlockType(state, payload) {
                       return {
                        ...state,
                        countBlockType: payload
                       }
                   },

        
    },    
    effects: dispatch => ({
        // handle state changes with impure functions.
        // use async/await for async actions
        async incrementAsync(payload, rootState) {
            await new Promise(resolve => setTimeout(resolve, 1000))
            dispatch.count.increment(payload)
        },
    }),
}