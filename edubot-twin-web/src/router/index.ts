import { createRouter, createWebHashHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import type { App } from 'vue'
import { Layout, getParentLayout } from '@/utils/routerHelper'
import { useI18n } from '@/hooks/web/useI18n'
import { NO_RESET_WHITE_LIST } from '@/constants'

const { t } = useI18n()

export const constantRouterMap: AppRouteRecordRaw[] = [
  {
    path: '/',
    component: Layout,
    name: 'Root',
    meta: {
      hidden: true
    }
  },
  {
    path: '/redirect',
    component: Layout,
    name: 'RedirectWrap',
    children: [
      {
        path: '/redirect/:path(.*)',
        name: 'Redirect',
        component: () => import('@/views/Redirect/Redirect.vue'),
        meta: {}
      }
    ],
    meta: {
      hidden: true,
      noTagsView: true
    }
  },
  {
    path: '/login',
    component: () => import('@/views/Login/Login.vue'),
    name: 'Login',
    meta: {
      hidden: true,
      title: t('router.login'),
      noTagsView: true
    }
  },
  {
    path: '/personal',
    component: Layout,
    redirect: '/personal/personal-center',
    name: 'Personal',
    meta: {
      title: t('router.personal'),
      hidden: true,
      canTo: true
    },
    children: [
      {
        path: 'personal-center',
        component: () => import('@/views/Personal/PersonalCenter/PersonalCenter.vue'),
        name: 'PersonalCenter',
        meta: {
          title: t('router.personalCenter'),
          hidden: true,
          canTo: true
        }
      }
    ]
  },
  {
    path: '/simulation',
    component: () => import('@/views/Simulation/Simulation.vue'),
    name: 'Simulation',
    meta: {
      hidden: true,
      title: t('router.simulation'),
      noTagsView: true,
      noCache: true
    }
  },
  {
    path: '/dry-run-simulation',
    component: () => import('@/views/Simulation/DryRunSimulation.vue'),
    name: 'DryRunSimulation',
    meta: {
      hidden: true,
      title: 'Dry Run 仿真',
      noTagsView: true,
      noCache: true
    }
  },
  {
    path: '/404',
    component: () => import('@/views/Error/404.vue'),
    name: 'NoFind',
    meta: {
      hidden: true,
      title: '404',
      noTagsView: true
    }
  }
]

export const asyncRouterMap: AppRouteRecordRaw[] = [
  {
    path: '/dashboard',
    component: Layout,
    redirect: '/dashboard/analysis',
    name: 'Dashboard',
    meta: {
      title: t('router.dashboard'),
      icon: 'vi-ant-design:dashboard-filled',
      alwaysShow: true
    },
    children: [
      {
        path: 'analysis',
        component: () => import('@/views/Dashboard/Analysis.vue'),
        name: 'Analysis',
        meta: {
          title: t('router.analysis'),
          noCache: true,
          affix: true
        }
      },
      {
        path: 'workplace',
        component: () => import('@/views/Dashboard/Workplace.vue'),
        name: 'Workplace',
        meta: {
          title: t('router.workplace'),
          noCache: true
        }
      }
    ]
  },
  {
    path: '/external-link',
    component: Layout,
    meta: {},
    name: 'ExternalLink',
    children: [
      {
        path: 'https://element-plus-admin-doc.cn/',
        name: 'DocumentLink',
        meta: {
          title: t('router.document'),
          icon: 'vi-clarity:document-solid'
        }
      }
    ]
  },
  {
    path: '/guide',
    component: Layout,
    name: 'Guide',
    meta: {},
    children: [
      {
        path: 'index',
        component: () => import('@/views/Guide/Guide.vue'),
        name: 'GuideDemo',
        meta: {
          title: t('router.guide'),
          icon: 'vi-cib:telegram-plane'
        }
      }
    ]
  },
  {
    path: '/components',
    component: Layout,
    name: 'ComponentsDemo',
    meta: {
      title: t('router.component'),
      icon: 'vi-bx:bxs-component',
      alwaysShow: true
    },
    children: [
      {
        path: 'form',
        component: getParentLayout(),
        redirect: '/components/form/default-form',
        name: 'Form',
        meta: {
          title: t('router.form'),
          alwaysShow: true
        },
        children: [
          {
            path: 'default-form',
            component: () => import('@/views/Components/Form/DefaultForm.vue'),
            name: 'DefaultForm',
            meta: {
              title: t('router.defaultForm')
            }
          },
          {
            path: 'use-form',
            component: () => import('@/views/Components/Form/UseFormDemo.vue'),
            name: 'UseForm',
            meta: {
              title: 'UseForm'
            }
          }
        ]
      },
      {
        path: 'table',
        component: getParentLayout(),
        redirect: '/components/table/default-table',
        name: 'TableDemo',
        meta: {
          title: t('router.table'),
          alwaysShow: true
        },
        children: [
          {
            path: 'default-table',
            component: () => import('@/views/Components/Table/DefaultTable.vue'),
            name: 'DefaultTable',
            meta: {
              title: t('router.defaultTable')
            }
          },
          {
            path: 'use-table',
            component: () => import('@/views/Components/Table/UseTableDemo.vue'),
            name: 'UseTable',
            meta: {
              title: 'UseTable'
            }
          },
          {
            path: 'tree-table',
            component: () => import('@/views/Components/Table/TreeTable.vue'),
            name: 'TreeTable',
            meta: {
              title: t('router.treeTable')
            }
          },
          {
            path: 'table-image-preview',
            component: () => import('@/views/Components/Table/TableImagePreview.vue'),
            name: 'TableImagePreview',
            meta: {
              title: t('router.PicturePreview')
            }
          },
          {
            path: 'table-video-preview',
            component: () => import('@/views/Components/Table/TableVideoPreview.vue'),
            name: 'TableVideoPreview',
            meta: {
              title: t('router.tableVideoPreview')
            }
          },
          {
            path: 'card-table',
            component: () => import('@/views/Components/Table/CardTable.vue'),
            name: 'CardTable',
            meta: {
              title: t('router.cardTable')
            }
          }
        ]
      },
      {
        path: 'editor-demo',
        component: getParentLayout(),
        redirect: '/components/editor-demo/editor',
        name: 'EditorDemo',
        meta: {
          title: t('router.editor'),
          alwaysShow: true
        },
        children: [
          {
            path: 'editor',
            component: () => import('@/views/Components/Editor/Editor.vue'),
            name: 'Editor',
            meta: {
              title: t('router.richText')
            }
          },
          {
            path: 'json-editor',
            component: () => import('@/views/Components/Editor/JsonEditor.vue'),
            name: 'JsonEditor',
            meta: {
              title: t('router.jsonEditor')
            }
          }
        ]
      },
      {
        path: 'search',
        component: () => import('@/views/Components/Search.vue'),
        name: 'Search',
        meta: {
          title: t('router.search')
        }
      },
      {
        path: 'descriptions',
        component: () => import('@/views/Components/Descriptions.vue'),
        name: 'Descriptions',
        meta: {
          title: t('router.descriptions')
        }
      },
      {
        path: 'image-viewer',
        component: () => import('@/views/Components/ImageViewer.vue'),
        name: 'ImageViewer',
        meta: {
          title: t('router.imageViewer')
        }
      },
      {
        path: 'dialog',
        component: () => import('@/views/Components/Dialog.vue'),
        name: 'Dialog',
        meta: {
          title: t('router.dialog')
        }
      },
      {
        path: 'icon',
        component: () => import('@/views/Components/Icon.vue'),
        name: 'Icon',
        meta: {
          title: t('router.icon')
        }
      },
      {
        path: 'icon-picker',
        component: () => import('@/views/Components/IconPicker.vue'),
        name: 'IconPicker',
        meta: {
          title: t('router.iconPicker')
        }
      },
      {
        path: 'echart',
        component: () => import('@/views/Components/Echart.vue'),
        name: 'Echart',
        meta: {
          title: t('router.echart')
        }
      },
      {
        path: 'count-to',
        component: () => import('@/views/Components/CountTo.vue'),
        name: 'CountTo',
        meta: {
          title: t('router.countTo')
        }
      },
      {
        path: 'qrcode',
        component: () => import('@/views/Components/Qrcode.vue'),
        name: 'Qrcode',
        meta: {
          title: t('router.qrcode')
        }
      },
      {
        path: 'highlight',
        component: () => import('@/views/Components/Highlight.vue'),
        name: 'Highlight',
        meta: {
          title: t('router.highlight')
        }
      },
      {
        path: 'infotip',
        component: () => import('@/views/Components/Infotip.vue'),
        name: 'Infotip',
        meta: {
          title: t('router.infotip')
        }
      },
      {
        path: 'input-password',
        component: () => import('@/views/Components/InputPassword.vue'),
        name: 'InputPassword',
        meta: {
          title: t('router.inputPassword')
        }
      },
      {
        path: 'waterfall',
        component: () => import('@/views/Components/Waterfall.vue'),
        name: 'waterfall',
        meta: {
          title: t('router.waterfall')
        }
      },
      {
        path: 'image-cropping',
        component: () => import('@/views/Components/ImageCropping.vue'),
        name: 'ImageCropping',
        meta: {
          title: t('router.imageCropping')
        }
      },
      {
        path: 'video-player',
        component: () => import('@/views/Components/VideoPlayer.vue'),
        name: 'VideoPlayer',
        meta: {
          title: t('router.videoPlayer')
        }
      },
      {
        path: 'avatars',
        component: () => import('@/views/Components/Avatars.vue'),
        name: 'Avatars',
        meta: {
          title: t('router.avatars')
        }
      },
      {
        path: 'i-agree',
        component: () => import('@/views/Components/IAgree.vue'),
        name: 'IAgree',
        meta: {
          title: t('router.iAgree')
        }
      }
    ]
  },
  {
    path: '/function',
    component: Layout,
    redirect: '/function/multipleTabs',
    name: 'Function',
    meta: {
      title: t('router.function'),
      icon: 'vi-ri:function-fill',
      alwaysShow: true
    },
    children: [
      {
        path: 'multiple-tabs',
        component: () => import('@/views/Function/MultipleTabs.vue'),
        name: 'MultipleTabs',
        meta: {
          title: t('router.multipleTabs')
        }
      },
      {
        path: 'multiple-tabs-demo/:id',
        component: () => import('@/views/Function/MultipleTabsDemo.vue'),
        name: 'MultipleTabsDemo',
        meta: {
          hidden: true,
          title: t('router.details'),
          canTo: true,
          activeMenu: '/function/multiple-tabs'
        }
      },
      {
        path: 'request',
        component: () => import('@/views/Function/Request.vue'),
        name: 'Request',
        meta: {
          title: t('router.request')
        }
      },
      {
        path: 'test',
        component: () => import('@/views/Function/Test.vue'),
        name: 'Test',
        meta: {
          title: t('router.permission'),
          permission: ['add', 'edit', 'delete']
        }
      }
    ]
  },
  {
    path: '/hooks',
    component: Layout,
    redirect: '/hooks/useWatermark',
    name: 'Hooks',
    meta: {
      title: 'hooks',
      icon: 'vi-ic:outline-webhook',
      alwaysShow: true
    },
    children: [
      {
        path: 'useWatermark',
        component: () => import('@/views/hooks/useWatermark.vue'),
        name: 'UseWatermark',
        meta: {
          title: 'useWatermark'
        }
      },
      {
        path: 'useTagsView',
        component: () => import('@/views/hooks/useTagsView.vue'),
        name: 'UseTagsView',
        meta: {
          title: 'useTagsView'
        }
      },
      {
        path: 'useValidator',
        component: () => import('@/views/hooks/useValidator.vue'),
        name: 'UseValidator',
        meta: {
          title: 'useValidator'
        }
      },
      {
        path: 'useCrudSchemas',
        component: () => import('@/views/hooks/useCrudSchemas.vue'),
        name: 'UseCrudSchemas',
        meta: {
          title: 'useCrudSchemas'
        }
      },
      {
        path: 'useClipboard',
        component: () => import('@/views/hooks/useClipboard.vue'),
        name: 'UseClipboard',
        meta: {
          title: 'useClipboard'
        }
      },
      {
        path: 'useNetwork',
        component: () => import('@/views/hooks/useNetwork.vue'),
        name: 'UseNetwork',
        meta: {
          title: 'useNetwork'
        }
      }
    ]
  },
  {
    path: '/level',
    component: Layout,
    redirect: '/level/menu1/menu1-1/menu1-1-1',
    name: 'Level',
    meta: {
      title: t('router.level'),
      icon: 'vi-carbon:skill-level-advanced'
    },
    children: [
      {
        path: 'menu1',
        name: 'Menu1',
        component: getParentLayout(),
        redirect: '/level/menu1/menu1-1/menu1-1-1',
        meta: {
          title: t('router.menu1')
        },
        children: [
          {
            path: 'menu1-1',
            name: 'Menu11',
            component: getParentLayout(),
            redirect: '/level/menu1/menu1-1/menu1-1-1',
            meta: {
              title: t('router.menu11'),
              alwaysShow: true
            },
            children: [
              {
                path: 'menu1-1-1',
                name: 'Menu111',
                component: () => import('@/views/Level/Menu111.vue'),
                meta: {
                  title: t('router.menu111')
                }
              }
            ]
          },
          {
            path: 'menu1-2',
            name: 'Menu12',
            component: () => import('@/views/Level/Menu12.vue'),
            meta: {
              title: t('router.menu12')
            }
          }
        ]
      },
      {
        path: 'menu2',
        name: 'Menu2',
        component: () => import('@/views/Level/Menu2.vue'),
        meta: {
          title: t('router.menu2')
        }
      }
    ]
  },
  {
    path: '/example',
    component: Layout,
    redirect: '/example/example-dialog',
    name: 'Example',
    meta: {
      title: t('router.example'),
      icon: 'vi-ep:management',
      alwaysShow: true
    },
    children: [
      {
        path: 'example-dialog',
        component: () => import('@/views/Example/Dialog/ExampleDialog.vue'),
        name: 'ExampleDialog',
        meta: {
          title: t('router.exampleDialog')
        }
      },
      {
        path: 'example-page',
        component: () => import('@/views/Example/Page/ExamplePage.vue'),
        name: 'ExamplePage',
        meta: {
          title: t('router.examplePage')
        }
      },
      {
        path: 'example-add',
        component: () => import('@/views/Example/Page/ExampleAdd.vue'),
        name: 'ExampleAdd',
        meta: {
          title: t('router.exampleAdd'),
          noTagsView: true,
          noCache: true,
          hidden: true,
          canTo: true,
          activeMenu: '/example/example-page'
        }
      },
      {
        path: 'example-edit',
        component: () => import('@/views/Example/Page/ExampleEdit.vue'),
        name: 'ExampleEdit',
        meta: {
          title: t('router.exampleEdit'),
          noTagsView: true,
          noCache: true,
          hidden: true,
          canTo: true,
          activeMenu: '/example/example-page'
        }
      },
      {
        path: 'example-detail',
        component: () => import('@/views/Example/Page/ExampleDetail.vue'),
        name: 'ExampleDetail',
        meta: {
          title: t('router.exampleDetail'),
          noTagsView: true,
          noCache: true,
          hidden: true,
          canTo: true,
          activeMenu: '/example/example-page'
        }
      }
    ]
  },
  {
    path: '/error',
    component: Layout,
    redirect: '/error/404',
    name: 'Error',
    meta: {
      title: t('router.errorPage'),
      icon: 'vi-ci:error',
      alwaysShow: true
    },
    children: [
      {
        path: '404-demo',
        component: () => import('@/views/Error/404.vue'),
        name: '404Demo',
        meta: {
          title: '404'
        }
      },
      {
        path: '403-demo',
        component: () => import('@/views/Error/403.vue'),
        name: '403Demo',
        meta: {
          title: '403'
        }
      },
      {
        path: '500-demo',
        component: () => import('@/views/Error/500.vue'),
        name: '500Demo',
        meta: {
          title: '500'
        }
      }
    ]
  },
  {
    path: '/authorization',
    component: Layout,
    redirect: '/authorization/user',
    name: 'Authorization',
    meta: {
      title: t('router.authorization'),
      icon: 'vi-eos-icons:role-binding',
      alwaysShow: true
    },
    children: [
      {
        path: 'department',
        component: () => import('@/views/Authorization/Department/Department.vue'),
        name: 'Department',
        meta: {
          title: t('router.department')
        }
      },
      {
        path: 'user',
        component: () => import('@/views/Authorization/User/User.vue'),
        name: 'User',
        meta: {
          title: t('router.user')
        }
      },
      {
        path: 'menu',
        component: () => import('@/views/Authorization/Menu/Menu.vue'),
        name: 'Menu',
        meta: {
          title: t('router.menuManagement')
        }
      },
      {
        path: 'role',
        component: () => import('@/views/Authorization/Role/Role.vue'),
        name: 'Role',
        meta: {
          title: t('router.role')
        }
      }
    ]
  },
  // ── 教师端路由（各页面提升为一级菜单）──────────────────────────────────────
  {
    path: '/teacher/home',
    component: Layout,
    name: 'TeacherHomeWrap',
    meta: {},
    children: [
      {
        path: '',
        component: () => import('@/views/Teacher/Home.vue'),
        name: 'TeacherHome',
        meta: { title: t('router.teacherHome'), icon: 'vi-carbon:home', noCache: true }
      }
    ]
  },
  {
    path: '/teacher/students',
    component: Layout,
    name: 'TeacherStudentsWrap',
    meta: {},
    children: [
      {
        path: '',
        component: () => import('@/views/Teacher/Students/Student.vue'),
        name: 'TeacherStudents',
        meta: { title: t('router.studentManagement'), icon: 'vi-carbon:user-multiple' }
      }
    ]
  },
  {
    path: '/teacher/experiments',
    component: Layout,
    name: 'TeacherExperiments',
    meta: {
      title: t('router.teacherExperiments'),
      icon: 'vi-carbon:chemistry',
      alwaysShow: true
    },
    children: [
      {
        path: 'list',
        component: () => import('@/views/Teacher/Experiments/ExperimentList.vue'),
        name: 'TeacherExperimentList',
        meta: { title: '实验列表', icon: 'vi-carbon:list' }
      },
      {
        path: ':id/detail',
        component: () => import('@/views/Teacher/Experiments/ExperimentDetail.vue'),
        name: 'TeacherExperimentDetail',
        meta: {
          title: '版本管理',
          noTagsView: true,
          noCache: true,
          hidden: true,
          canTo: true,
          activeMenu: '/teacher/experiments/list'
        }
      },
      {
        path: 'files',
        component: () => import('@/views/Teacher/Experiments/ExperimentFiles.vue'),
        name: 'TeacherExperimentFiles',
        meta: { title: '实验文件', icon: 'vi-carbon:folder' }
      },
      {
        path: 'environments',
        component: () => import('@/views/Teacher/Experiments/ExperimentEnvs.vue'),
        name: 'TeacherExperimentEnvs',
        meta: { title: '实验环境', icon: 'vi-carbon:settings' }
      }
    ]
  },
  {
    path: '/teacher/exams',
    component: Layout,
    name: 'TeacherExams',
    meta: { title: '考试管理', icon: 'vi-carbon:exam-mode', alwaysShow: true },
    children: [
      {
        path: 'list',
        component: () => import('@/views/Teacher/Exams/ExamList.vue'),
        name: 'TeacherExamList',
        meta: { title: '考试列表', icon: 'vi-carbon:list' }
      },
      {
        path: ':id/detail',
        component: () => import('@/views/Teacher/Exams/ExamDetail.vue'),
        name: 'TeacherExamDetail',
        meta: {
          title: '考试详情',
          noTagsView: true,
          noCache: true,
          hidden: true,
          canTo: true,
          activeMenu: '/teacher/exams/list'
        }
      },
      {
        path: 'envs',
        component: () => import('@/views/Teacher/Exams/ExamEnvs.vue'),
        name: 'TeacherExamEnvs',
        meta: { title: '考试环境', icon: 'vi-carbon:settings' }
      },
      {
        path: 'files',
        component: () => import('@/views/Teacher/Exams/ExamFiles.vue'),
        name: 'TeacherExamFiles',
        meta: { title: '考试文件', icon: 'vi-carbon:folder' }
      },
      {
        path: 'eval-scripts',
        component: () => import('@/views/Teacher/Exams/ExamEvalScripts.vue'),
        name: 'TeacherExamEvalScripts',
        meta: { title: '测评脚本', icon: 'vi-carbon:script' }
      },
      {
        path: 'attempts',
        component: () => import('@/views/Teacher/Exams/ExamAttemptsManager.vue'),
        name: 'TeacherExamAttemptsManager',
        meta: { title: '尝试管理', icon: 'vi-carbon:task-settings' }
      },
      {
        path: 'review-list',
        component: () => import('@/views/Teacher/Exams/ExamReviewList.vue'),
        name: 'TeacherExamReviewList',
        meta: { title: '复核列表', icon: 'vi-carbon:review' }
      },
      {
        path: 'attempts/:attempt_id/review',
        component: () => import('@/views/Teacher/Exams/ExamAttemptReview.vue'),
        name: 'TeacherExamAttemptReview',
        meta: {
          title: '考试复核',
          noTagsView: true,
          noCache: true,
          hidden: true,
          canTo: true,
          activeMenu: '/teacher/exams/list'
        }
      },
      {
        path: 'attempts/:attempt_id/submission',
        component: () => import('@/views/Teacher/Exams/ExamAttemptSubmission.vue'),
        name: 'TeacherExamAttemptSubmission',
        meta: {
          title: '查看提交代码',
          noTagsView: true,
          noCache: true,
          hidden: true,
          canTo: true,
          activeMenu: '/teacher/exams/list'
        }
      }
    ]
  },
  {
    path: '/teacher/grade-preview',
    component: Layout,
    name: 'TeacherGradePreviewWrap',
    meta: {},
    children: [
      {
        path: '',
        component: () => import('@/views/Teacher/Exams/TeacherGradePreview.vue'),
        name: 'TeacherGradePreview',
        meta: { title: '成绩预览', icon: 'vi-carbon:chart-bar' }
      }
    ]
  },
  {
    path: '/teacher/containers',
    component: Layout,
    name: 'TeacherContainers',
    meta: {
      title: t('router.containerManagement'),
      icon: 'vi-carbon:container-software',
      alwaysShow: true
    },
    children: [
      {
        path: 'monitor',
        component: () => import('@/views/Teacher/Containers/Monitor.vue'),
        name: 'ContainerMonitor',
        meta: { title: t('router.containerMonitor'), icon: 'vi-carbon:dashboard' }
      },
      {
        path: 'config',
        component: () => import('@/views/Teacher/Containers/Config.vue'),
        name: 'ContainerConfig',
        meta: { title: '容器配置', icon: 'vi-carbon:settings' }
      }
    ]
  },
  // ── 学生端路由（各页面提升为一级菜单）──────────────────────────────────────
  {
    path: '/student/home',
    component: Layout,
    name: 'StudentHomeWrap',
    meta: {},
    children: [
      {
        path: '',
        component: () => import('@/views/Student/Home.vue'),
        name: 'StudentHome',
        meta: { title: t('router.studentHome'), icon: 'vi-carbon:home', noCache: true, affix: true }
      }
    ]
  },
  {
    path: '/student/files',
    component: Layout,
    name: 'StudentFilesWrap',
    meta: {},
    children: [
      {
        path: '',
        component: () => import('@/views/Student/FileManager.vue'),
        name: 'StudentFileManager',
        meta: { title: '文件管理', icon: 'vi-carbon:folder' }
      }
    ]
  },
  {
    path: '/student/editor',
    component: Layout,
    name: 'StudentEditorWrap',
    meta: {},
    children: [
      {
        path: '',
        component: () => import('@/views/Student/CodeEditor.vue'),
        name: 'StudentCodeEditor',
        meta: { title: '代码编辑器', icon: 'vi-carbon:code' }
      }
    ]
  },
  {
    path: '/student/grades',
    component: Layout,
    name: 'StudentGradesWrap',
    meta: {},
    children: [
      {
        path: '',
        component: () => import('@/views/Student/Grades.vue'),
        name: 'StudentGrades',
        meta: { title: '我的成绩', icon: 'vi-carbon:certificate' }
      },
      {
        path: ':exam_id',
        component: () => import('@/views/Student/StudentGradeDetail.vue'),
        name: 'StudentGradeDetail',
        meta: {
          title: '成绩详情',
          noTagsView: true,
          noCache: true,
          hidden: true,
          canTo: true,
          activeMenu: '/student/grades'
        }
      },
      {
        path: ':exam_id/attempt/:attempt_id/code',
        component: () => import('@/views/Student/StudentAttemptCodeView.vue'),
        name: 'StudentAttemptCodeView',
        meta: {
          title: '查看提交代码',
          noTagsView: true,
          noCache: true,
          hidden: true,
          canTo: true,
          activeMenu: '/student/grades'
        }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  strict: true,
  routes: constantRouterMap as RouteRecordRaw[],
  scrollBehavior: () => ({ left: 0, top: 0 })
})

export const resetRouter = (): void => {
  router.getRoutes().forEach((route) => {
    const { name } = route
    if (name && !NO_RESET_WHITE_LIST.includes(name as string)) {
      router.hasRoute(name) && router.removeRoute(name)
    }
  })
}

export const setupRouter = (app: App<Element>) => {
  app.use(router)
}

export default router
