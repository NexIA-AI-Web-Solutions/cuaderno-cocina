<template>
    <v-container>
        <native-recipe-access-notice v-if="!useUserPreferenceStore().canWriteNativeRecipes" :access="useUserPreferenceStore().nativeRecipeWriteAccess" />
        <exchange-panel :read-only="!useUserPreferenceStore().canWriteNativeRecipes" />
        <v-row v-if="useUserPreferenceStore().canWriteNativeRecipes">
            <v-col>


                <v-stepper v-model="stepper">
                    <template v-slot:default="{ prev, next }">
                        <v-stepper-header>
                            <v-stepper-item :title="$t('Type')" value="type" icon=" "></v-stepper-item>
                            <v-divider></v-divider>

                            <template v-if="['url','ai', 'source'].includes(importType)">
                                <v-stepper-item :title="$t('Import')" value="url" icon=" "></v-stepper-item>
                                <v-divider></v-divider>
                                <template v-if="importResponse.duplicates && importResponse.duplicates.length > 0">
                                    <v-stepper-item :title="$t('Duplicate')" value="duplicates" icon=" "></v-stepper-item>
                                    <v-divider></v-divider>
                                </template>
                                <v-stepper-item :title="$t('Image')" value="image_chooser" icon=" "></v-stepper-item>
                                <v-divider></v-divider>
                                <v-stepper-item :title="$t('Keywords')" value="keywords_chooser" icon=" "></v-stepper-item>
                                <v-divider></v-divider>
                                <v-stepper-item :title="$t('Steps')" value="step_editor" icon=" "></v-stepper-item>
                                <v-divider></v-divider>
                                <v-stepper-item :title="$t('Save')" value="confirm" icon=" "></v-stepper-item>
                            </template>
                            <template v-if="importType == 'app'">
                                <v-stepper-item :title="$t('App')" value="app" icon=" "></v-stepper-item>
                                <v-divider></v-divider>
                                <v-stepper-item :title="$t('File')" value="file" icon=" "></v-stepper-item>
                                <v-divider></v-divider>
                                <v-stepper-item :title="$t('Import')" value="import_log" icon=" "></v-stepper-item>
                            </template>

                            <template v-if="importType == 'bookmarklet'">
                                <v-stepper-item :title="$t('Bookmarklet')" value="bookmarklet" icon=" "></v-stepper-item>
                            </template>

                            <template v-if="importType == 'url-list'">
                                <v-stepper-item :title="$t('UrlList')" value="url_list_input" icon=" "></v-stepper-item>
                                <v-divider></v-divider>
                                <v-stepper-item :title="$t('Import')" value="url_list_import" icon=" "></v-stepper-item>
                            </template>

                        </v-stepper-header>

                        <v-stepper-window>
                            <v-stepper-window-item value="type">
                                <v-row>
                                    <v-col cols="12" md="6">
                                        <v-card
                                            :title="$t('Url_Import')"
                                            :subtitle="$t('UrlImportSubtitle')"
                                            prepend-icon="$import"
                                            variant="outlined"
                                            :color="(importType == 'url') ? 'primary' : ''"
                                            elevation="1"
                                            @click="importType = 'url'">
                                        </v-card>
                                    </v-col>

                                    <v-col cols="12" md="6" v-if="useUserPreferenceStore().activeSpace.aiEnabled">
                                        <v-card
                                            :title="$t('AI')"
                                            :subtitle="$t('AIImportSubtitle')"
                                            prepend-icon="$ai"
                                            variant="outlined"
                                            :color="(importType == 'ai') ? 'primary' : ''"
                                            elevation="1"
                                            @click="importType = 'ai'"
                                            :disabled="!useUserPreferenceStore().activeSpace.aiEnabled">
                                        </v-card>
                                    </v-col>

                                    <v-col cols="12" md="6">
                                        <v-card
                                            :title="$t('App')"
                                            :subtitle="$t('AppImportSubtitle')"
                                            prepend-icon="fa-solid fa-folder-open"
                                            variant="outlined"
                                            :color="(importType == 'app') ? 'primary' : ''"
                                            elevation="1"
                                            @click="importType = 'app'">
                                        </v-card>
                                    </v-col>
                                    <v-col cols="12" md="6">
                                        <v-card
                                            :title="$t('Bookmarklet')"
                                            :subtitle="$t('BookmarkletImportSubtitle')"
                                            prepend-icon="fa-solid fa-bookmark"
                                            variant="outlined"
                                            :color="(importType == 'bookmarklet') ? 'primary' : ''"
                                            elevation="1"
                                            @click="importType = 'bookmarklet'">
                                        </v-card>
                                    </v-col>
                                    <v-col cols="12" md="6">
                                        <v-card
                                            title="JSON/HTML"
                                            :subtitle="$t('SourceImportSubtitle')"
                                            prepend-icon="fa-solid fa-code"
                                            variant="outlined"
                                            :color="(importType == 'source') ? 'primary' : ''"
                                            elevation="1"
                                            @click="importType = 'source'">
                                        </v-card>
                                    </v-col>
                                    <v-col cols="12" md="6">
                                        <v-card
                                            :title="$t('UrlList')"
                                            :subtitle="$t('UrlListSubtitle')"
                                            prepend-icon="fa-solid fa-list"
                                            variant="outlined"
                                            :color="(importType == 'url-list') ? 'primary' : ''"
                                            elevation="1"
                                            @click="importType = 'url-list'">
                                        </v-card>
                                    </v-col>
                                </v-row>
                                <v-stepper-actions>
                                    <template #prev>
                                        <v-spacer></v-spacer>
                                    </template>
                                    <template #next>
                                        <v-btn @click="stepper = 'url'" v-if="['url','ai', 'source'].includes(importType)" color="success">{{ $t('Next') }}</v-btn>
                                        <v-btn @click="stepper = 'app'" v-if="importType == 'app'" color="success">{{ $t('Next') }}</v-btn>
                                        <v-btn @click="stepper = 'bookmarklet'" v-if="importType == 'bookmarklet'" color="success">{{ $t('Next') }}</v-btn>
                                        <v-btn @click="stepper = 'url_list_input'" v-if="importType == 'url-list'" color="success">{{ $t('Next') }}</v-btn>
                                    </template>
                                </v-stepper-actions>
                            </v-stepper-window-item>

                            <!-- ------------ -->
                            <!-- ULR/AI Items -->
                            <!-- ------------ -->

                            <v-stepper-window-item value="url">
                                <v-text-field :label="$t('Website') + ' (https://...)'" v-model="importUrl" v-if="importType == 'url'" :loading="loading" autofocus
                                              @keydown.enter="loadRecipeFromUrl({url: importUrl})"></v-text-field>

                                <div v-if="importType == 'ai'">
                                    <v-row>
                                        <v-col cols="12" md="6">
                                            <v-model-select model="AiProvider" v-model="selectedAiProvider" hide-details>
                                                <template #append>
                                                    <v-btn icon="$settings" :to="{name:'ModelListPage', params: {model: 'AiProvider'}}" color="success"></v-btn>
                                                </template>
                                            </v-model-select>
                                        </v-col>
                                        <v-col cols="12" md="6">
                                            <v-btn-toggle class="mb-2" border divided v-model="aiMode">
                                                <v-btn value="file">{{ $t('File') }}</v-btn>
                                                <v-btn value="text">{{ $t('Text') }}</v-btn>
                                            </v-btn-toggle>
                                        </v-col>
                                    </v-row>


                                    <v-file-upload v-model="image" v-if="aiMode == 'file'" :loading="loading" clearable>
                                        <template #icon>
                                            <v-icon icon="fa-solid fa-file-pdf"></v-icon>
                                            {{ $t('or') }}
                                            <v-icon icon="fa-solid fa-file-image"></v-icon>
                                        </template>
                                    </v-file-upload>

                                    <v-textarea v-model="sourceImportText" :loading="loading" autofocus v-if="aiMode == 'text'"
                                                @keydown.enter="loadRecipeFromAiImport()"></v-textarea>
                                </div>

                                <v-textarea v-model="sourceImportText" label="JSON/HTML" :loading="loading" v-if="importType == 'source'" :hint="$t('SourceImportHelp')"
                                            persistent-hint autofocus @keydown.enter="loadRecipeFromUrl({data: sourceImportText})"></v-textarea>

                                <v-alert v-if="importResponse.error" :title="$t('Error')" :text="importResponse.msg" color="warning">

                                </v-alert>

                                <v-stepper-actions>
                                    <template #prev>
                                        <v-btn @click="stepper = 'type'; importResponse = {}">{{ $t('Back') }}</v-btn>
                                    </template>
                                    <template #next>
                                        <v-btn @click="loadRecipeFromUrl({url: importUrl})" v-if="importType == 'url'" :disabled="importUrl == ''" :loading="loading">{{
                                                $t('Load')
                                            }}
                                        </v-btn>
                                        <v-btn @click="loadRecipeFromUrl({data: sourceImportText})" v-if="importType == 'source'" :disabled="sourceImportText == ''"
                                               :loading="loading">{{ $t('Load') }}
                                        </v-btn>
                                        <v-btn @click="loadRecipeFromAiImport()" v-if="importType == 'ai'"
                                               :disabled="(aiMode == 'file' && image == null) || (aiMode == 'text' && sourceImportText == '')" :loading="loading">{{ $t('Load') }}
                                        </v-btn>
                                    </template>
                                </v-stepper-actions>
                            </v-stepper-window-item>
                            <v-stepper-window-item value="duplicates">
                                <v-alert variant="tonal" v-if="importResponse.duplicates && importResponse.duplicates.length > 0">
                                    <v-alert-title>{{ $t('Duplicate') }}</v-alert-title>
                                    {{ $t('DuplicateFoundInfo') }}
                                    <v-list>
                                        <v-list-item :to="{name: 'RecipeViewPage', params: {id: r.id}}" v-for="r in importResponse.duplicates" :key="r.id"> {{ r.name }}
                                            (#{{ r.id }})
                                        </v-list-item>
                                    </v-list>
                                </v-alert>
                                <v-stepper-actions>
                                    <template #prev>
                                        <v-btn @click="stepper = 'url'">{{ $t('Back') }}</v-btn>
                                    </template>
                                    <template #next>
                                        <v-btn @click="stepper = 'image_chooser'">{{ $t('Next') }}</v-btn>
                                    </template>
                                </v-stepper-actions>
                            </v-stepper-window-item>
                            <v-stepper-window-item value="image_chooser" v-if="importResponse.recipe">
                                <v-row>
                                    <v-col cols="12" md="6">
                                        <h2 class="text-h5">{{ $t('Selected') }}</h2>
                                        <v-img max-height="30vh" :src="importResponse.recipe.imageUrl"></v-img>
                                    </v-col>
                                    <v-col cols="12" md="6">
                                        <h2 class="text-h5">{{ $t('Available') }}</h2>
                                        <v-row dense>
                                            <v-col cols="4" v-for="i in importResponse.images">
                                                <v-img max-height="10vh" cover aspect-ratio="1" :src="i" @click="importResponse.recipe.imageUrl = i"></v-img>
                                            </v-col>
                                        </v-row>
                                    </v-col>
                                </v-row>
                                <v-stepper-actions>
                                    <template #prev>
                                        <v-btn @click="stepper = 'duplicates'" v-if="importResponse.duplicates && importResponse.duplicates.length > 0">{{ $t('Back') }}</v-btn>
                                        <v-btn @click="stepper = 'url'" v-else>{{ $t('Back') }}</v-btn>
                                    </template>
                                    <template #next>
                                        <v-btn @click="stepper = 'keywords_chooser'">{{ $t('Next') }}</v-btn>
                                    </template>
                                </v-stepper-actions>
                            </v-stepper-window-item>
                            <v-stepper-window-item value="keywords_chooser" v-if="importResponse.recipe">
                                <v-row>
                                    <v-col class="text-center">
                                        <v-btn-group border divided>
                                            <ai-action-button 
                                                :text="$t('Auto_Sort')" 
                                                prepend-icon="$ai" 
                                                :loading="aiStepSortLoading" 
                                                @selected="aiStepSort" 
                                                :disabled="!importResponse.recipe?.steps || importResponse.recipe.steps.length < 1">
                                            </ai-action-button>
                                            
                                            <v-btn prepend-icon="fa-solid fa-maximize" @click="handleSplitAllSteps()">
                                                <span v-if="!mobile">{{ $t('Split') }}</span>
                                            </v-btn>
                                            
                                            <v-btn prepend-icon="fa-solid fa-minimize" @click="handleMergeAllSteps()">
                                                <span v-if="!mobile">{{ $t('Merge') }}</span>
                                            </v-btn>
                                        </v-btn-group>
                                    </v-col>
                                </v-row>

                                <v-row>
                                    <v-col>
                                        <v-model-select model="Keyword" v-model="keywordSelect" create>
                                            <template #append>
                                                <v-btn icon="$add" color="success"
                                                       @click="addSelectedKeyword"
                                                       :disabled="keywordSelect == null"></v-btn>
                                            </template>
                                        </v-model-select>
                                    </v-col>
                                </v-row>

                                <v-list>
                                    <v-list-item border v-for="k in importResponse.recipe.keywords" :key="k.id ?? k.name" :class="{'bg-success': k.importKeyword}"
                                                 @click="k.importKeyword = !k.importKeyword">
                                        {{ k.label }}
                                        <template #append>
                                            <v-checkbox-btn :model-value="k.importKeyword"></v-checkbox-btn>
                                        </template>
                                    </v-list-item>
                                </v-list>

                                <v-stepper-actions>
                                    <template #prev>
                                        <v-btn @click="stepper = 'image_chooser'">{{ $t('Back') }}</v-btn>
                                    </template>
                                    <template #next>
                                        <v-btn @click="stepper = 'step_editor'">{{ $t('Next') }}</v-btn>
                                    </template>
                                </v-stepper-actions>
                            </v-stepper-window-item>
                            <v-stepper-window-item value="step_editor" v-if="importResponse.recipe">
                                <v-row>
                                    <v-col class="text-center">
                                        <v-btn-group border divided>
                                            <v-btn prepend-icon="fa-solid fa-shuffle" @click="autoSortIngredients()"><span v-if="!mobile">{{ $t('Auto_Sort') }}</span></v-btn>
                                            <v-btn prepend-icon="fa-solid fa-maximize" @click="handleSplitAllSteps()"><span v-if="!mobile">{{ $t('Split') }}</span></v-btn>
                                            <v-btn prepend-icon="fa-solid fa-minimize" @click="handleMergeAllSteps()"><span v-if="!mobile">{{ $t('Merge') }}</span></v-btn>
                                        </v-btn-group>
                                    </v-col>
                                </v-row>
                                <v-row v-for="(s, stepIndex) in importResponse.recipe.steps" :key="stepIndex">
                                    <v-col cols="12">
                                        <v-chip color="primary">#{{ stepIndex + 1 }}</v-chip>
                                        <v-btn variant="plain" size="small" icon class="float-right">
                                            <v-icon icon="$menu"></v-icon>
                                            <v-menu activator="parent">
                                                <v-list>
                                                    <v-list-item prepend-icon="$delete" @click="deleteStep(s)">{{ $t('Delete') }}</v-list-item>
                                                    <v-list-item prepend-icon="fa-solid fa-maximize" @click="importResponse.recipe && splitStep(importResponse.recipe.steps, s, '\n')">{{ $t('Split') }}</v-list-item>
                                                </v-list>
                                            </v-menu>
                                        </v-btn>
                                    </v-col>
                                    <v-col cols="12" md="6">
                                        <v-list>
                                            <vue-draggable v-model="s.ingredients" group="ingredients" handle=".drag-handle" :empty-insert-threshold="25">
                                                <v-list-item v-for="(i, ingredientIndex) in s.ingredients" border>
                                                    <v-icon size="small" class="drag-handle cursor-grab mr-2" icon="$dragHandle"></v-icon>
                                                    <v-chip density="compact" label class="mr-1">{{ i.amount }}</v-chip>
                                                    <v-chip density="compact" label class="mr-1" v-if="i.unit">{{ i.unit.name }}</v-chip>
                                                    <v-chip density="compact" label class="mr-1" v-if="i.food">{{ i.food.name }}</v-chip>
                                                    <template #append>
                                                        <v-btn variant="plain" size="small" icon class="float-right">
                                                            <v-icon icon="$menu"></v-icon>
                                                            <v-menu activator="parent">
                                                                <v-list>
                                                                    <v-list-item prepend-icon="$edit" @click="editingIngredient = i; dialog=true">{{ $t('Edit') }}</v-list-item>
                                                                    <v-list-item prepend-icon="$delete" @click="deleteIngredient(s,i)">{{ $t('Delete') }}</v-list-item>
                                                                    <v-list-item prepend-icon="fa-solid fa-sort"
                                                                                 @click="editingIngredientIndex = ingredientIndex; editingStepIndex = stepIndex; editingStep = s;  dialogIngredientSorter = true">
                                                                        {{ $t('Move') }}
                                                                    </v-list-item>
                                                                </v-list>
                                                            </v-menu>
                                                        </v-btn>
                                                    </template>
                                                </v-list-item>
                                            </vue-draggable>
                                        </v-list>
                                    </v-col>
                                    <v-col cols="12" md="6">
                                        <v-textarea class="mt-2" v-model="s.instruction" auto-grow></v-textarea>
                                    </v-col>
                                    <v-divider></v-divider>
                                </v-row>
                                <v-row>
                                    <v-col class="text-center">
                                        <v-btn icon="$add" color="create" @click="addStep()"></v-btn>
                                    </v-col>
                                </v-row>
                                <v-dialog max-width="450px" v-model="dialog">
                                    <v-card>
                                        <v-closable-card-title v-model="dialog" :title="$t('Ingredient Editor')"></v-closable-card-title>
                                        <v-card-text>
                                            <v-text-field :label="$t('Original_Text')" v-model="editingIngredient.originalText" readonly></v-text-field>
                                            <v-text-field :label="$t('Amount')" v-model="editingIngredient.amount"></v-text-field>

                                            <v-text-field :label="$t('Unit')" v-model="editingIngredient.unit.name" :rules="['required']" v-if="editingIngredient.unit">
                                                <template #append-inner>
                                                    <v-btn icon="$delete" color="delete" @click="editingIngredient.unit = {name: ''}"></v-btn>
                                                </template>
                                            </v-text-field>
                                            <v-btn prepend-icon="$create" color="create" class="mb-4" @click="editingIngredient.unit = {name: ''}" v-else>{{ $t('Unit') }}</v-btn>

                                            <v-text-field :label="$t('Food')" v-model="editingIngredient.food.name"></v-text-field>
                                            <v-text-field :label="$t('Note')" v-model="editingIngredient.note"></v-text-field>
                                        </v-card-text>
                                        <v-card-actions>
                                            <v-btn class="float-right" color="save" @click="dialog = false">{{ $t('Save') }}</v-btn>
                                        </v-card-actions>
                                    </v-card>
                                </v-dialog>
                                <v-stepper-actions>
                                    <template #prev>
                                        <v-btn @click="stepper = 'keywords_chooser'">{{ $t('Back') }}</v-btn>
                                    </template>
                                    <template #next>
                                        <v-btn @click="stepper = 'confirm'">{{ $t('Next') }}</v-btn>
                                    </template>
                                </v-stepper-actions>
                            </v-stepper-window-item>
                            <v-stepper-window-item value="confirm" v-if="importResponse.recipe">
                                <v-card :loading="loading || fileApiLoading">
                                    <v-card-title>{{ importResponse.recipe.name }}</v-card-title>
                                    <v-row>
                                        <v-col cols="12" md="6">
                                            <v-img v-if="importResponse.recipe.imageUrl" :src="importResponse.recipe.imageUrl"></v-img>
                                        </v-col>
                                        <v-col cols="12" md="6">
                                            <v-text-field :label="$t('Name')" v-model="importResponse.recipe.name" :rules="[['maxLength',128]]"></v-text-field>
                                            <v-number-input :label="$t('Servings')" v-model="importResponse.recipe.servings" :precision="2"></v-number-input>
                                            <v-text-field :label="$t('ServingsText')" v-model="importResponse.recipe.servingsText" servings></v-text-field>
                                            <v-textarea :label="$t('Description')" v-model="importResponse.recipe.description" :rules="[['maxLength',512]]" counter
                                                        clearable></v-textarea>

                                            <v-checkbox v-model="editAfterImport" :label="$t('Edit_Recipe')" hide-details></v-checkbox>
                                        </v-col>

                                    </v-row>

                                </v-card>
                                <v-stepper-actions>
                                    <template #prev>
                                        <v-btn @click="stepper = 'step_editor'">{{ $t('Back') }}</v-btn>
                                    </template>
                                    <template #next>
                                        <v-btn @click="createRecipeFromImport()" :disabled="false" color="success">{{ $t('Import') }}</v-btn>
                                    </template>
                                </v-stepper-actions>
                            </v-stepper-window-item>

                            <!-- ---------------- -->
                            <!-- App Import Items -->
                            <!-- ---------------- -->

                            <v-stepper-window-item value="app">

                                <v-row>
                                    <v-col cols="12" md="3" v-for="i in INTEGRATIONS">
                                        <v-card prepend-icon="fa-solid fa-carrot" :title="i.name" :subtitle="i.description" @click="importApp = i.id" variant="outlined" elevation="1"
                                                :color="(importApp == i.id) ? 'primary' : ''">
                                            <template #append>
                                                <v-btn icon="$help" variant="plain" :href="i.helpUrl" target="_blank"></v-btn>
                                            </template>
                                        </v-card>
                                    </v-col>
                                </v-row>

                                <v-stepper-actions>
                                    <template #prev>
                                        <v-btn @click="stepper = 'type'">{{ $t('Back') }}</v-btn>
                                    </template>
                                    <template #next>
                                        <v-btn @click="stepper = 'file'">{{ $t('Next') }}</v-btn>
                                    </template>
                                </v-stepper-actions>
                            </v-stepper-window-item>
                            <v-stepper-window-item value="file">
                                <v-file-upload v-model="appImportFiles" multiple></v-file-upload>

                                <v-alert variant="outlined" elevation="1" density="compact" :title="$t('Duplicate')" :text="$t('import_duplicates')" class="mt-2">
                                    <template #prepend>
                                        <v-checkbox v-model="appImportDuplicates"></v-checkbox>
                                    </template>
                                </v-alert>
                                <div v-if="importApp == 'MEALIE1'">
                                    <v-checkbox v-model="appImportMealPlans" :label="$t('ImportMealPlans')" hide-details></v-checkbox>
                                    <v-checkbox v-model="appImportShoppingLists" :label="$t('ImportShoppingList')" hide-details></v-checkbox>
                                    <v-checkbox v-model="appImportNutritionsPerServing" :label="$t('NutritionsPerServing')" :hint="$t('NutritionsPerServingHelp')" persistent-hint></v-checkbox>
                                </div>

                                <v-stepper-actions>
                                    <template #prev>
                                        <v-btn @click="stepper = 'app'">{{ $t('Back') }}</v-btn>
                                    </template>
                                    <template #next>
                                        <v-btn @click="appImport()" :disabled="appImportFiles.length == 0" :loading="fileApiLoading">{{ $t('Import') }}</v-btn>
                                    </template>
                                </v-stepper-actions>
                            </v-stepper-window-item>
                            <v-stepper-window-item value="import_log">

                                <import-log-viewer :import-log="appImportLog" v-if="appImportLog"></import-log-viewer>

                                <v-stepper-actions>
                                    <template #prev>
                                        <v-btn @click="stepper = 'file'">{{ $t('Back') }}</v-btn>
                                    </template>
                                    <template #next>
                                        <v-btn :to="{name: 'SearchPage', query: {keywords: appImportLog.keyword.id}}" v-if="appImportLog && !appImportLog.running"
                                               :disabled="false">{{ $t('View_Recipes') }}
                                        </v-btn>
                                    </template>
                                </v-stepper-actions>
                            </v-stepper-window-item>

                            <!-- ------------ -->
                            <!-- Bookmarklet  -->
                            <!-- ------------ -->
                            <v-stepper-window-item value="bookmarklet">
                                {{ $t('BookmarkletImportSubtitle') }}

                                <ol>
                                    <li>1. {{ $t('BookmarkletHelp1') }}</li>
                                    <li>
                                        <v-btn :href="bookmarkletContent" color="primary">{{ $t('ImportIntoTandoor') }}</v-btn>
                                    </li>
                                    <li>2. {{ $t('BookmarkletHelp2') }}</li>
                                    <li>3. {{ $t('BookmarkletHelp3') }}</li>
                                </ol>

                                <v-stepper-actions>
                                    <template #prev>
                                        <v-btn @click="stepper = 'type'">{{ $t('Back') }}</v-btn>
                                    </template>
                                    <template #next>

                                    </template>
                                </v-stepper-actions>
                            </v-stepper-window-item>

                            <!-- ---------------- -->
                            <!-- URL List         -->
                            <!-- ---------------- -->

                            <v-stepper-window-item value="url_list_input">

                                <v-textarea :hint="$t('one_url_per_line')" auto-grow max-rows="20" persistent-hint v-model="urlListImportInput">

                                </v-textarea>

                                <v-stepper-actions>
                                    <template #prev>
                                        <v-btn @click="stepper = 'type'">{{ $t('Back') }}</v-btn>
                                    </template>
                                    <template #next>
                                        <v-btn @click="stepper = 'url_list_import'; doListImport()" :disabled="urlListImportInput.length == 0">{{ $t('Import') }}</v-btn>
                                    </template>
                                </v-stepper-actions>
                            </v-stepper-window-item>

                            <v-stepper-window-item value="url_list_import">

                                <v-progress-linear color="primary" :height="24" :model-value="urlListImportedRecipes.length / urlListImportInput.split('\n').length * 100">
                                    {{ urlListImportedRecipes.length }} / {{ urlListImportInput.split('\n').length }}
                                </v-progress-linear>

                                <v-list>
                                    <v-list-item border v-for="r in urlListImportedRecipes" :title="r.name" :subtitle="r.sourceUrl ?? undefined" :key="r.id"
                                                 :to="{name: 'RecipeViewPage', params: {id: r.id}}" target="_blank">

                                    </v-list-item>
                                </v-list>

                                <v-stepper-actions>
                                    <template #prev>
                                        <v-btn @click="stepper = 'url_list_input'">{{ $t('Back') }}</v-btn>
                                    </template>
                                    <template #next>
                                        <v-btn @click="resetImporter()" :disabled="loading">{{ $t('Reset') }}</v-btn>
                                    </template>
                                </v-stepper-actions>
                            </v-stepper-window-item>


                        </v-stepper-window>
                    </template>
                </v-stepper>
            </v-col>
        </v-row>
        <v-row v-if="useUserPreferenceStore().canWriteNativeRecipes" dense>
            <v-col class="text-center">
                <v-btn size="small" prepend-icon="fa-solid fa-arrow-rotate-left" variant="tonal" color="warning" @click="resetImporter()">{{ $t('Reset') }}</v-btn>
            </v-col>
        </v-row>
    </v-container>

    <step-ingredient-sorter-dialog v-if="useUserPreferenceStore().canWriteNativeRecipes && importResponse.recipe" :step-index="editingStepIndex" :step="editingStep" :recipe="importResponse.recipe" v-model="dialogIngredientSorter"
                                   :ingredient-index="editingIngredientIndex"></step-ingredient-sorter-dialog>

</template>

<script lang="ts" setup>

import {useI18n} from "vue-i18n";
import {computed, onMounted, onUnmounted, ref, watch} from "vue";
import {
    AccessToken,
    AiProvider,
    ApiApi,
    ImportLog,
    Recipe,
    type RecipeFromSourceRequest, Keyword, RecipeRequest, SourceImportRecipe,
    RecipeFromSourceResponse,
    type SourceImportIngredient,
    SourceImportKeyword,
    SourceImportStep,
    Step
} from "@/openapi";
import {ErrorMessageType, MessageType, PreparedMessage, useMessageStore} from "@/stores/MessageStore";
import {useRouter} from "vue-router";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore";
import {VueDraggable} from "vue-draggable-plus";
import VClosableCardTitle from "@/components/dialogs/VClosableCardTitle.vue";
import {useFileApi} from "@/composables/useFileApi";
import ModelSelect from "@/components/inputs/ModelSelect.vue";
import {useDisplay} from "vuetify";
import {useUrlSearchParams} from "@vueuse/core";
import {INTEGRATIONS} from "@/utils/integration_utils";
import {VFileUpload} from 'vuetify/labs/VFileUpload'
import ImportLogViewer from "@/components/display/ImportLogViewer.vue";
import {DateTime} from "luxon";
import {useDjangoUrls} from "@/composables/useDjangoUrls";
import bookmarkletJs from '@/assets/bookmarklet_v3?url'
import StepIngredientSorterDialog from "@/components/dialogs/StepIngredientSorterDialog.vue";
import {mergeAllSteps, splitAllSteps, splitStep} from "@/utils/step_utils.ts";
import VModelSelect from "@/components/inputs/VModelSelect.vue";
import {SourceImportPrecisionError, sourceImportRequest, sourcePreviewIngredientAmount} from "@/utils/sourceImport";
import ExchangePanel from "@/cuaderno/components/ExchangePanel.vue";
import NativeRecipeAccessNotice from '@/cuaderno/components/NativeRecipeAccessNotice.vue';
import {nativeRecipeWriteMessage} from '@/cuaderno/nativeRecipeWriteUi';

function ensureCanImportRecipes(): boolean {
    const store = useUserPreferenceStore()
    if (store.canWriteNativeRecipes) return true
    useMessageStore().addMessage(MessageType.WARNING, {title: 'Permisos de recetas', text: nativeRecipeWriteMessage(store.nativeRecipeWriteAccess)}, 8000)
    return false
}

function doListImport() {
    if (!ensureCanImportRecipes()) return
    urlList.value = urlListImportInput.value.split('\n')
    loading.value = true
    importFromUrlList()
}

async function importFromUrlList() {
    if (!ensureCanImportRecipes()) {loading.value = false; return}
    if (disposed) return
    const api = new ApiApi()
    let url = urlList.value.pop()
    while (url != undefined && url.trim() === '') url = urlList.value.pop()
    if (url === undefined) {
        useMessageStore().addPreparedMessage(PreparedMessage.CREATE_SUCCESS)
        loading.value = false
        return
    }
    loading.value = true
    let sourceResponse: RecipeFromSourceResponse
    try {
        sourceResponse = await api.apiRecipeFromSourceCreate({recipeFromSource: {url}})
        if (!sourceResponse.recipe) throw new Error('La fuente no contiene una receta importable')
    } catch (err: any) {
        if (disposed) return
        if (err?.response?.status === 429) useMessageStore().addPreparedMessage(PreparedMessage.RATE_LIMIT, err)
        else useMessageStore().addMessage(MessageType.WARNING, t('ErrorUrlListImport'), 8000, url)
        urlListImportInput.value = [url, ...urlList.value].join('\n')
        stepper.value = 'url_list_input'
        loading.value = false
        return
    }
    if (disposed) return
    try {
        if (!ensureCanImportRecipes()) {loading.value = false; return}
        const recipe = await api.apiRecipeCreate({recipe: sourceImportRequest(sourceResponse.recipe)})
        if (disposed) return
        urlListImportedRecipes.value.push(recipe)
        if (!ensureCanImportRecipes()) {loading.value = false; return}
        try {
            await updateRecipeImage(recipe.id!, null, sourceResponse.recipe.imageUrl)
        } catch (err) {
            if (!disposed) useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err)
        }
    } catch (err) {
        if (!disposed) useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
    }
    if (!disposed) {
        batchTimer = setTimeout(() => {
            batchTimer = undefined
            void importFromUrlList()
        }, 500)
    }
}

const aiStepSortLoading = ref(false)
const params = useUrlSearchParams('history', {})
const {mobile} = useDisplay()
const router = useRouter()
const {t} = useI18n()
const {updateRecipeImage, doAiImport, doAppImport, fileApiLoading} = useFileApi()
const {getFullUrl} = useDjangoUrls()

const bookmarkletContent = computed(() => {
    const config = JSON.stringify({
        url: getFullUrl('/api/bookmarklet-import/'),
        redirect: getFullUrl('/recipe/import/'),
        token: bookmarkletToken.value,
    })
    const scriptUrl = new URL(bookmarkletJs, new URL('static/vue3/', document.baseURI)).href
    return 'javascript:(function(){' +
        `const config=${config};` +
        'if(window.cuadernoBookmarklet!==undefined){window.cuadernoBookmarklet(config);}' +
        'else{const script=document.createElement("script");' +
        'script.onload=function(){window.cuadernoBookmarklet(config);};' +
        `script.src=${JSON.stringify(scriptUrl)};document.body.appendChild(script);}` +
        '})()'
})

const importType = ref<'url' | 'ai' | 'app' | 'bookmarklet' | 'source' | 'url-list'>("url")
const importApp = ref('DEFAULT')
const stepper = ref("type")
const dialog = ref(false)

const loading = ref(false)
let disposed = false
let previewRevision = 0
let pollTimer: ReturnType<typeof setTimeout> | undefined
let batchTimer: ReturnType<typeof setTimeout> | undefined
let bookmarkletRequest: Promise<void> | undefined

const importUrl = ref("")

const urlListImportInput = ref("")
const urlList = ref([] as string[])
const urlListImportedRecipes = ref([] as Recipe[])

const sourceImportText = ref("")
const appImportFiles = ref<File[]>([])
const appImportDuplicates = ref(false)
const appImportMealPlans = ref(true)
const appImportShoppingLists = ref(true)
const appImportNutritionsPerServing = ref(false)
const appImportLog = ref<null | ImportLog>(null)
const image = ref<File>()
const aiMode = ref<'file' | 'text'>('file')
const selectedAiProvider = ref<undefined | AiProvider>(useUserPreferenceStore().activeSpace.aiDefaultProvider ?? undefined)
const editAfterImport = ref(false)

const bookmarkletToken = ref("")

const importResponse = ref<RecipeFromSourceResponse>({})
const keywordSelect = ref<Keyword | null>(null)
const editingIngredient = ref<SourceImportIngredient>({food: {name: ''}, unit: {name: ''}, amount: 0, originalText: ''})

// stuff for ingredient mover, find some better solution at some point (finally merge importer/editor?)
const editingIngredientIndex = ref(0)
const dialogIngredientSorter = ref(false)
const editingStep = ref<Step | SourceImportStep>({} as Step)
const editingStepIndex = ref(0)

let sharedImportStarted = false
function startSharedImport() {
    if (sharedImportStarted || !useUserPreferenceStore().canWriteNativeRecipes) return
    sharedImportStarted = true
    // handle manifest share intend passing url to import page
    if (params.url && typeof params.url === "string") {
        importUrl.value = params.url
        loadRecipeFromUrl({url: importUrl.value})
    }
    else if (params.text && typeof params.text === "string") {
        importUrl.value = params.text
        loadRecipeFromUrl({url: importUrl.value})
    }

    else if (params.bookmarklet_import && typeof params.bookmarklet_import === "string" && !isNaN(parseInt(params.bookmarklet_import))) {
        importType.value = 'url'
        loadRecipeFromUrl({bookmarklet: parseInt(params.bookmarklet_import)})
    }
}
onMounted(startSharedImport)
watch(() => useUserPreferenceStore().canWriteNativeRecipes, allowed => {if (allowed) startSharedImport()})

onUnmounted(() => {
    disposed = true
    previewRevision++
    if (pollTimer !== undefined) clearTimeout(pollTimer)
    if (batchTimer !== undefined) clearTimeout(batchTimer)
})

watch(importType, selected => {
    if (selected === 'bookmarklet') void loadOrCreateBookmarkletToken()
})

/**
 * call server to load recipe from a given URl
 */
function loadRecipeFromUrl(recipeFromSourceRequest: RecipeFromSourceRequest) {
    if (!ensureCanImportRecipes()) return
    const api = new ApiApi()
    const revision = ++previewRevision
    loading.value = true
    importResponse.value = {}
    return api.apiRecipeFromSourceCreate({recipeFromSource: recipeFromSourceRequest}).then(r => {
        if (disposed || revision !== previewRevision) return
        if (r.recipeId != null) return router.push({name: 'RecipeViewPage', params: {id: r.recipeId}})
        importResponse.value = r
        if (r.duplicates && r.duplicates.length > 0) stepper.value = 'duplicates'
        else stepper.value = r.images && r.images.length > 0 ? 'image_chooser' : 'keywords_chooser'
    }).catch(async (err: any) => {
        if (disposed || revision !== previewRevision) return
        let response: RecipeFromSourceResponse | undefined
        try {
            if (typeof err?.response?.json === 'function') response = await err.response.json()
        } catch { /* Network and non-JSON failures use the original error below. */ }
        if (disposed || revision !== previewRevision) return
        if (response?.error) importResponse.value = response
        else useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    }).finally(() => {
        if (!disposed && revision === previewRevision) loading.value = false
    })
}

/**
 * upload file to conversion endpoint
 */
function loadRecipeFromAiImport() {
    if (!ensureCanImportRecipes()) return
    let request = null

    if (selectedAiProvider.value == undefined) {
        useMessageStore().addError(ErrorMessageType.CREATE_ERROR, "No AI Provider selected")
        return
    }

    if (image.value != null && aiMode.value == 'file') {
        request = doAiImport(selectedAiProvider.value.id!, image.value)
    } else if (sourceImportText.value != '' && aiMode.value == 'text') {
        request = doAiImport(selectedAiProvider.value.id!, null, sourceImportText.value)
    }

    if (request != null) {
        loading.value = true
        const revision = ++previewRevision
        return request.then(r => {
            if (disposed || revision !== previewRevision) return
            importResponse.value = r

            if (!importResponse.value.error) {
                if (importResponse.value.images && importResponse.value.images.length > 0) {
                    stepper.value = 'image_chooser'
                } else {
                    stepper.value = 'keywords_chooser'
                }
            }
        }).catch(err => {
            if (!disposed && revision === previewRevision) useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
        }).finally(() => {
            if (!disposed && revision === previewRevision) loading.value = false
        })
    }

}

function appImport() {
    if (!ensureCanImportRecipes()) return
    return doAppImport(appImportFiles.value, importApp.value, appImportDuplicates.value, appImportMealPlans.value, appImportShoppingLists.value, appImportNutritionsPerServing.value).then(id => {
        if (disposed) return
        stepper.value = 'import_log'
        return recLoadImportLog(id)
    }).catch(err => {
        if (!disposed) useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
    })
}

function recLoadImportLog(importLogId: number) {
    if (disposed) return Promise.resolve()
    if (pollTimer !== undefined) clearTimeout(pollTimer)
    const api = new ApiApi()
    return api.apiImportLogRetrieve({id: importLogId}).then(r => {
        if (disposed) return
        appImportLog.value = r
        if (r.running) {
            pollTimer = setTimeout(() => {
                pollTimer = undefined
                void recLoadImportLog(importLogId)
            }, 1000)
        }
    }).catch(err => {
        if (!disposed) useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    })
}

/** Create a recipe once, then treat an optional image failure separately. */
async function createRecipeFromImport() {
    if (!ensureCanImportRecipes()) return
    const source = importResponse.value.recipe
    if (!source || loading.value || disposed) return
    const api = new ApiApi()
    loading.value = true
    const request = sourceImportRequest({...source, keywords: (source.keywords ?? []).filter(k => k.importKeyword)})
    try {
        const recipe = await api.apiRecipeCreate({recipe: request})
        try {
            if (ensureCanImportRecipes()) await updateRecipeImage(recipe.id!, null, source.imageUrl)
        } catch (err) {
            if (!disposed) useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err)
        }
        if (!disposed) {
            await router.push(editAfterImport.value && useUserPreferenceStore().canWriteNativeRecipes
                ? {name: 'ModelEditPage', params: {id: recipe.id, model: 'recipe'}}
                : {name: 'RecipeViewPage', params: {id: recipe.id}})
        }
    } catch (err) {
        if (!disposed) useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
    } finally {
        if (!disposed) loading.value = false
    }
}

/**
 * deletes the given step from the local recipe
 * @param step step to delete
 */
function deleteStep(step: SourceImportStep) {
    if (importResponse.value.recipe) {
        importResponse.value.recipe.steps.splice(importResponse.value.recipe.steps.findIndex(x => x === step), 1)
    }
}

function handleMergeAllSteps(): void {
    if (importResponse.value.recipe && importResponse.value.recipe.steps) {
        importResponse.value.recipe.steps = mergeAllSteps(importResponse.value.recipe.steps)
    }
}

function handleSplitAllSteps(): void {
    if (importResponse.value.recipe && importResponse.value.recipe.steps) {
        splitAllSteps(importResponse.value.recipe.steps, '\n')
    }
}

/**
 * Merge two steps (the given and next one)
 */
function mergeStep(step: SourceImportStep) {
    if (importResponse.value.recipe) {
        let step_index = importResponse.value.recipe.steps.findIndex(x => x === step)
        let removed_steps = importResponse.value.recipe.steps.splice(step_index, 2)

        importResponse.value.recipe.steps.splice(step_index, 0, {
            instruction: removed_steps.flatMap(x => x.instruction).join('\n'),
            ingredients: removed_steps.flatMap(x => x.ingredients),
            showIngredientsTable: useUserPreferenceStore().userSettings.showStepIngredients!
        })
    } else {
        useMessageStore().addMessage(MessageType.ERROR, "no steps found to split")
    }

}

/**
 * deletes the given ingredient from the given step
 * @param step step to delete ingredient from
 * @param ingredient ingredient to delete
 */
function deleteIngredient(step: SourceImportStep, ingredient: SourceImportIngredient) {
    step.ingredients = step.ingredients.filter(i => i != ingredient)
}

/**
 * sort steps and ingredients using AI and update recipe with result
 * @param providerId provider to use for request
 */
function aiStepSort(providerId: number) {
    if (!ensureCanImportRecipes()) return
    if (!importResponse.value.recipe) return;

    let api = new ApiApi()
    aiStepSortLoading.value = true

    api.apiAiStepSortCreate({recipe: sourceImportRequest(importResponse.value.recipe), provider: providerId}).then(r => {
        importResponse.value.recipe = importedRecipePreview(r)
    }).catch(err => {
        if (err instanceof SourceImportPrecisionError) {
            useMessageStore().addMessage(MessageType.ERROR, {title: 'Revisa las cantidades', text: err.message}, 8000)
        } else {
            useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
        }
    }).finally(() => {
        aiStepSortLoading.value = false
    })
}

/**
 * automatically assign ingredients to steps based on text matching
 */
function autoSortIngredients() {
    if (importResponse.value.recipe) {
        let ingredients = importResponse.value.recipe.steps.flatMap(s => s.ingredients)
        importResponse.value.recipe.steps.forEach(s => s.ingredients = [])

        ingredients.forEach(i => {
            let found = false
            importResponse.value.recipe!.steps.forEach(s => {
                if (s.instruction.toLowerCase().includes(i.food.name.trim().toLowerCase()) && !found) {
                    found = true
                    s.ingredients.push(i)
                }
            })
            if (!found) {
                importResponse.value.recipe!.steps[0]?.ingredients.push(i)
            }
            // TODO implement a new "second try" algorithm if no exact match was found
            /*

             if (!found) {
                let best_match = {rating: 0, step: importResponse.value.recipe.steps[0]}
                importResponse.value.recipe.steps.forEach(s => {

                    let match = stringSimilarity.findBestMatch(i.food.name.trim(), s.instruction.split(' '))

                    if (match.bestMatch.rating > best_match.rating) {
                        best_match = {rating: match.bestMatch.rating, step: s}
                    }
                })
                best_match.step.ingredients.push(i)
                found = true
            }
             */
        })
    } else {
        useMessageStore().addMessage(MessageType.ERROR, "no steps found to split")
    }
}

/**
 * set the import status for all keywords to the given status
 * @param status if keyword should be imported or not
 */
function setAllKeywordsImportStatus(status: boolean) {
    importResponse.value.recipe?.keywords?.forEach(keyword => {
        keyword.importKeyword = status
    })
}

/**
 * add a new (empty) step at the end of the step list
 */
function addStep() {
    importResponse.value.recipe?.steps.push({
        ingredients: [],
        instruction: ''
    } as SourceImportStep)
}


/**
 * load or create an AccessToken with the bookmarklet scope for use in the bookmarklet code
 */
function loadOrCreateBookmarkletToken(): Promise<void> {
    if (!ensureCanImportRecipes()) return Promise.resolve()
    if (bookmarkletToken.value || disposed) return Promise.resolve()
    if (bookmarkletRequest) return bookmarkletRequest
    const api = new ApiApi()
    bookmarkletRequest = api.apiAccessTokenList().then(async tokens => {
        if (disposed || !ensureCanImportRecipes()) return
        const existing = tokens.find(token => token.scope === 'bookmarklet')
        const token = existing ?? await api.apiAccessTokenCreate({accessToken: {
            scope: 'bookmarklet', expires: DateTime.now().plus({year: 100}).toJSDate()
        } as AccessToken})
        if (!disposed) bookmarkletToken.value = token.token
    }).catch(err => {
        if (!disposed) useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    }).finally(() => { bookmarkletRequest = undefined })
    return bookmarkletRequest
}

/**
 * reset the importer at any point
 */
function resetImporter() {
    location.reload()
}

function addSelectedKeyword() {
    const keyword = keywordSelect.value
    const recipe = importResponse.value.recipe
    if (!keyword || !recipe) return
    recipe.keywords ??= []
    recipe.keywords.push({id: keyword.id, name: keyword.name, label: keyword.name, importKeyword: true})
    keywordSelect.value = null
}

function importedRecipePreview(recipe: Recipe): SourceImportRecipe {
    return {
        ...recipe,
        sourceUrl: recipe.sourceUrl ?? '',
        description: recipe.description ?? '',
        keywords: (recipe.keywords ?? []).map(keyword => ({id: keyword.id, name: keyword.name, label: keyword.name, importKeyword: true})),
        properties: (recipe.properties ?? []).filter(property => property.propertyAmount != null).map(property => ({
            propertyType: property.propertyType, propertyAmount: property.propertyAmount ?? 0,
        })),
        steps: recipe.steps.map(step => ({
            ...step, instruction: step.instruction ?? '',
            ingredients: (step.ingredients ?? []).map(ingredient => ({
                ...ingredient, amount: sourcePreviewIngredientAmount(ingredient.amount),
                food: ingredient.food ?? {name: ''}, unit: ingredient.unit ?? {name: ''},
                note: ingredient.note ?? '', originalText: ingredient.originalText ?? '',
            })),
        })),
    }
}

</script>

<style scoped>

</style>
